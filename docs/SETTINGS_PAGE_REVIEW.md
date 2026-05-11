# Admin Settings Page — Full Code Review

**Scope:** Everything behind `/users/settings/` (14 URL patterns)  
**Files reviewed:**
- `project/armguard/apps/users/views.py` (all settings-related FBVs + `SystemSettingsView`, lines 725–1835)
- `project/armguard/apps/users/models.py` (`SystemSettings`, lines 392–637)
- `project/armguard/templates/users/settings.html` (1,183 lines)
- `project/armguard/static/js/settings.js` (181 lines)

---

## Summary Table

| # | Severity | Area | Finding |
|---|----------|------|---------|
| SETT-01 | 🔴 HIGH | Security / Audit | No AuditLog written when settings are saved |
| SETT-02 | 🔴 HIGH | Data Integrity | `truncate_data` multi-step SQL is not atomic |
| SETT-03 | 🟠 MEDIUM | Logic | `_psi_fields` fallback uses doctrinal defaults, not current DB values |
| SETT-04 | 🟠 MEDIUM | Bug | DB size always `'—'` in production (PostgreSQL path mismatch) |
| SETT-05 | 🟠 MEDIUM | Security | OREX simulation TOCTOU race (duplicate run possible) |
| SETT-06 | 🟡 LOW | Bug | Orphan media cleanup misses files when Personnel ID contains underscores |
| SETT-07 | 🟡 LOW | HTTP Semantics | `simulate_orex_status_json` (GET) performs a state-mutating `UPDATE` |
| SETT-08 | 🟡 LOW | Consistency | `storage_status_json` / `cleanup_orphaned_personnel_media` lack `@login_required` |
| SETT-09 | ℹ️ INFO | Code Quality | `_group_guard` re-checks `is_authenticated` inside a `@login_required` chain |
| SETT-10 | ℹ️ INFO | Code Quality | `SystemSettingsView` guard pattern is non-standard (returns `None` on success) |

---

## SETT-01 — 🔴 HIGH — No AuditLog on Settings Save

**Location:** `SystemSettingsView.post()` (~line 800–1002 of `views.py`)

**Issue:**  
`SystemSettingsView.post()` calls `obj.save()` as its last action and immediately returns a success redirect. No `AuditLog` or `ActivityLog` entry is written for the settings change. This means a superuser can silently make any of the following changes with zero audit trail:

- Disable MFA site-wide (`mfa_required = False`)
- Reduce `password_min_length` to 1
- Set session timeout for all roles to `0` (never expire)
- Change `commander_name` / `commander_rank` in reports
- Alter per-purpose weapon visibility or loadout defaults

An attacker who gains superuser access can disable MFA, log in as any user, then re-enable MFA — leaving no evidence in `AuditLog`.

**Contrast:** `truncate_data` correctly writes a summarising `AuditLog` entry. `SystemSettingsView` does not.

**Fix:**
```python
# After obj.save() in SystemSettingsView.post():
from armguard.apps.users.models import AuditLog, _get_client_ip, _get_user_agent
AuditLog.objects.create(
    user=request.user,
    action='UPDATE',
    model_name='SystemSettings',
    object_pk=str(obj.pk),
    message=f'System settings updated by {request.user.username}.',
    ip_address=_get_client_ip(request),
    user_agent=_get_user_agent(request),
)
```

For high-value fields (`mfa_required`, `password_min_length`, `password_history_count`, session timeouts), log the before/after values:
```python
obj_before = SystemSettings.get()
# ... apply changes ...
obj.save()
changed_fields = [
    f'{f}: {getattr(obj_before, f)} → {getattr(obj, f)}'
    for f in ('mfa_required', 'password_min_length', 'password_history_count',
              'timeout_system_admin', 'timeout_armorer', 'timeout_superuser')
    if getattr(obj_before, f) != getattr(obj, f)
]
```

---

## SETT-02 — 🔴 HIGH — `truncate_data` Multi-step SQL is Not Atomic

**Location:** `truncate_data` (~line 1220–1330 of `views.py`)

**Issue:**  
The truncation operation executes four sequential raw SQL steps inside `with _db_conn.cursor() as _cur:`:

1. `UPDATE` — Restore magazine/ammunition/accessory pool quantities
2. `DELETE FROM transactions` (and/or `transaction_logs`, `snapshots`)
3. `UPDATE personnel` — Clear 36 issued-state columns
4. `UPDATE rifle/pistol` — Reset item status to `'Available'`

Django's database connection is in **autocommit mode by default**. `with _db_conn.cursor()` is a cursor lifecycle manager only — it does **not** open a database transaction. Each `_cur.execute()` commits immediately.

**Failure scenario:**
- Step 1 commits (pool quantities restored ✓)
- Step 2 commits (transactions deleted ✓)
- Step 3 raises an exception (e.g., column name mismatch after a schema migration)
- `except Exception` catches it, user sees a generic error
- **Result:** Transactions are deleted and pool quantities are restored, but Personnel records still show stale "issued" state and Rifle/Pistol items are still marked `'Issued'`. The DB is now inconsistent and cannot be repaired by running truncate again (the transactions to aggregate from are gone).

**Fix:**
```python
from django.db import transaction as _txn

try:
    with _txn.atomic():                      # ← add this
        with _db_conn.cursor() as _cur:
            # ... all four SQL steps ...
    # AuditLog + ActivityLog writes go OUTSIDE the atomic block
    # so they are always committed (even if atomic() commits the data)
    if deleted_summary:
        AuditLog.objects.create(...)
        ActivityLog.objects.create(...)
        messages.success(...)
    else:
        messages.warning(...)
except Exception as _exc:
    ...
```

The `transaction.atomic()` wrapper means either all four steps commit together or none do, giving a clean rollback on any partial failure.

---

## SETT-03 — 🟠 MEDIUM — `_psi_fields` Fallback Silently Overwrites Customized Values

**Location:** `SystemSettingsView.post()`, `_psi_fields` loop (~line 980–999 of `views.py`)

**Issue:**
```python
_psi_fields = {
    'duty_sentinel_holster_qty': 1,   # ← doctrinal defaults
    'duty_sentinel_pistol_ammo_qty': 42,
    ...
}
for field, default in _psi_fields.items():
    try:
        val = max(0, int(request.POST.get(field, default)))  # ← fallback to doctrinal default
    except (ValueError, TypeError):
        val = default
    setattr(obj, field, val)
```

When a form field is **absent from `request.POST`**, `request.POST.get(field, default)` returns the **hardcoded doctrinal default** (e.g., `42` rounds for `duty_sentinel_pistol_ammo_qty`), not the value currently stored in the database.

**Trigger:** Browsers do not submit disabled `<input>` fields. If the UI conditionally disables loadout fields (e.g., because auto-consumables is off), those fields are absent from POST and silently revert to doctrinal values. Similarly, any partial API POST or a JS bug that removes an input will reset that loadout to its military doctrine default.

This also affects the 4 `max_*_qty` accessory cap fields and any other integer field managed by this loop.

**Fix:** Fall back to the object's current DB value, not the hardcoded default:
```python
val = max(0, int(request.POST.get(field, getattr(obj, field))))
```

Since `obj` is loaded at the top of `post()` via `SystemSettings.get()`, `getattr(obj, field)` is always available.

---

## SETT-04 — 🟠 MEDIUM — DB Size Always `'—'` in Production

**Location:** `storage_status_json` (~line 1795–1800 of `views.py`)

**Issue:**
```python
db_path = django_settings.DATABASES['default'].get('NAME', '')
try:
    db_bytes = os.path.getsize(str(db_path))   # ← treats DB name as a file path
    db_size  = _fmt(db_bytes)
except OSError:
    db_bytes = 0
    db_size  = '—'                              # ← always reached in production
```

In production, `DATABASES['default']['NAME']` = `'armguard'` (a PostgreSQL database name). `os.path.getsize('armguard')` raises `OSError: [Errno 2] No such file or directory: 'armguard'`. This is caught silently, and the DB size card in the Storage panel **always shows `'—'`** when deployed on PostgreSQL.

The code works correctly in development (SQLite) where `NAME` is a `pathlib.Path` object pointing to `db.sqlite3`.

**Fix:**
```python
engine = django_settings.DATABASES['default'].get('ENGINE', '')
if 'sqlite3' in engine:
    try:
        db_bytes = os.path.getsize(str(django_settings.DATABASES['default']['NAME']))
        db_size  = _fmt(db_bytes)
    except OSError:
        db_bytes, db_size = 0, '—'
elif 'postgresql' in engine:
    try:
        from django.db import connection as _pg_conn
        with _pg_conn.cursor() as cur:
            cur.execute('SELECT pg_database_size(current_database())')
            db_bytes = cur.fetchone()[0]
            db_size  = _fmt(db_bytes)
    except Exception:
        db_bytes, db_size = 0, '—'
else:
    db_bytes, db_size = 0, '—'
```

---

## SETT-05 — 🟠 MEDIUM — OREX Simulation TOCTOU Race

**Location:** `simulate_orex_run` (~line 1390–1410 of `views.py`)

**Issue:**
```python
# Check — not protected by a lock
if SimulationRun.objects.filter(status__in=['queued', 'running']).exists():
    messages.warning(request, 'A simulation is already in progress...')
    return redirect('dashboard')

# Create — separate transaction
run = SimulationRun.objects.create(...)
t = threading.Thread(target=_run_orex_background, ...)
t.start()
```

Two concurrent POST requests (e.g., a double-click or rapid form resubmit) can both execute the `exists()` check while no run is active, both receive `False`, and both proceed to `create()` + `Thread.start()`. Two background threads then run simultaneously, issuing rifles to the same personnel and depleting the same inventory pools, potentially issuing the same rifle to two different people.

This was previously flagged in the audit report as SEC-04.

**Fix:**
```python
from django.db import transaction as _txn

with _txn.atomic():
    # select_for_update() acquires a row-level lock.
    # For PostgreSQL this prevents the race entirely.
    active = SimulationRun.objects.select_for_update().filter(
        status__in=['queued', 'running']
    ).exists()
    if active:
        messages.warning(...)
        return redirect('dashboard')
    run = SimulationRun.objects.create(...)

t = threading.Thread(target=_run_orex_background, args=(str(run.run_id), request.user.pk), daemon=False)
t.start()
```

> **Note:** `select_for_update()` requires PostgreSQL. On SQLite it raises `DatabaseError`. Given that production uses PostgreSQL, this is the correct fix. Add a fallback comment for dev/test environments.

---

## SETT-06 — 🟡 LOW — Orphan Cleanup Misses Files When Personnel ID Contains Underscores

**Location:** `cleanup_orphaned_personnel_media` (~line 1858–1872 of `views.py`)

**Issue:**
```python
stem = os.path.splitext(name)[0]   # e.g. "IMG_REYES_DEL_PILAR_PAF-001"
parts = stem.split('_')
pid = parts[-1] if len(parts) >= 2 else None   # → "001" instead of "PAF-001"
```

Personnel image filenames follow the convention `IMG_<LastName>_<PersonnelID>`. If the last name contains underscores (`REYES_DEL_PILAR`), `split('_')[-1]` returns the last segment (`PAF-001`'s last underscore segment). However, if the Personnel ID itself contains an underscore (e.g. future schema change), or if the last name has an unexpected suffix, the parsed `pid` will not match `existing_ids` and the file will be considered an orphan when it isn't, causing **data loss** (deletion of valid files).

Conversely, with the current ID format (`PAF-001`), the `split('_')[-1]` = `'PAF-001'` works correctly. The bug is latent if the ID format ever changes.

The QR cleanup uses a safer approach (`stem.replace('_qr', '')`), but this would fail if the ID itself ends in `_qr`.

**Fix (defensive):** Use `rsplit('_', maxsplit=1)` to split only on the last underscore, regardless of how many underscores appear in the last name:
```python
# Only split on last underscore — handles multi-underscore last names
parts = stem.rsplit('_', maxsplit=1)
pid = parts[-1] if len(parts) == 2 else None
```

This matches `IMG_REYES_DEL_PILAR_PAF-001` → `pid = 'PAF-001'` correctly.

---

## SETT-07 — 🟡 LOW — GET Endpoint Performs State-Mutating UPDATE

**Location:** `simulate_orex_status_json` (~line 1672–1678 of `views.py`)

**Issue:**
```python
# Auto-expire runs stuck in queued/running for > 30 minutes
stale_cutoff = _tz.now() - datetime.timedelta(minutes=30)
SimulationRun.objects.filter(
    status__in=['queued', 'running'],
    started_at__lt=stale_cutoff,
).update(status='error', error_message='Run expired...', completed_at=_tz.now())
```

This is a `GET` endpoint (used by the dashboard polling widget) that executes a database `UPDATE` on every poll. This violates HTTP semantics — GET requests should be safe (no side effects) and idempotent.

**Practical impact:**
- Django's CSRF middleware does not protect GET requests. Any URL (even external) that causes a superuser's browser to load this endpoint will trigger the stale-expiry logic.
- Since this only changes stuck runs from `running` to `error`, the real-world harm is limited.
- More importantly: a 100ms polling interval × 9 Gunicorn workers means this UPDATE can fire up to 900 times per second when the dashboard is open.

**Fix:** Move the stale-expiry logic to a POST endpoint (e.g., `simulate_orex_reset`) or a scheduled task (e.g., `django-crontab` or Celery beat). The status endpoint should be read-only.

---

## SETT-08 — 🟡 LOW — Missing `@login_required` on JSON Endpoints

**Location:**
- `storage_status_json` (line 1753 of `views.py`)
- `cleanup_orphaned_personnel_media` (line 1832 of `views.py`)

**Issue:**
Both views use `if not _is_admin(request.user): return JsonResponse({'error': 'Forbidden'}, status=403)` as access control. This is **functionally correct** — `_is_admin()` returns `False` for unauthenticated users (`AnonymousUser.is_authenticated = False` is checked first). An unauthenticated request gets a `403` JSON response rather than a redirect to the login page.

However, without `@login_required`:
- Unauthenticated users receive `403 Forbidden` (JSON) instead of `302 → /login/`
- Inconsistent with every other view in `users/views.py` which uses `@login_required`
- If `_is_admin()` ever raises an exception for an `AnonymousUser` (e.g., if it begins accessing `user.profile`), it could produce a `500` instead of a graceful redirect

**Fix:** Add `@login_required` to both views:
```python
@login_required
def storage_status_json(request):
    ...

@require_POST
@login_required
def cleanup_orphaned_personnel_media(request):
    ...
```

---

## SETT-09 — ℹ️ INFO — Redundant `is_authenticated` Check in `_group_guard`

**Location:** `_group_guard` (~line 1009 of `views.py`)

```python
def _group_guard(request):
    """Return None if superuser, else a redirect."""
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
```

All callers (`group_add`, `group_rename`, `group_delete`, `squadron_add`, `squadron_rename`, `squadron_delete`) are decorated with `@login_required`, which guarantees `request.user.is_authenticated = True` before `_group_guard` is ever reached. The `is_authenticated` check inside the guard is therefore dead code — it will never be `False`.

This is defence-in-depth (not harmful), but the comment `"""Return None if superuser, else a redirect."""` is slightly misleading — it should say "redirect to dashboard if not a superuser".

---

## SETT-10 — ℹ️ INFO — Non-Standard Guard Pattern in `SystemSettingsView`

**Location:** `SystemSettingsView._guard()` (~line 730 of `views.py`)

**Issue:**
The view uses a bespoke `_guard()` helper that returns `None` on success and an `HttpResponse` redirect on failure:
```python
resp = self._guard(request)
if resp:
    return resp
```

This is a subtle pattern. `None` is falsy, so the check works. However:
- If a developer adds a new method to `SystemSettingsView` and forgets `if resp: return resp`, the guard silently passes for non-superusers.
- Django provides `UserPassesTestMixin` specifically for this purpose, which raises `PermissionDenied` (producing a `403`) or redirects, and cannot be accidentally skipped.

**Recommended pattern:**
```python
class SystemSettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    raise_exception = True  # 403 instead of redirect to login

    def test_func(self):
        return self.request.user.is_superuser
    ...
```

This eliminates the per-method guard call entirely.

---

## What Is Done Well

1. **CSRF on every form.** All 9 forms in `settings.html` include `{% csrf_token %}`. The main settings form, all group/squadron inline forms, the truncation form, and the OREX simulation form are all protected.

2. **Logo upload validation.** The logo upload flow validates file size (2 MB cap), verifies MIME type via Pillow (`JPEG/PNG/GIF/WEBP`), calls `.verify()` to detect corrupt/malicious images, and calls `seek(0)` before saving. This is a correct, defense-in-depth implementation.

3. **Weapon visibility validation.** The `at_least_one` guard in `post()` prevents saving a configuration where both pistol and rifle are hidden for a given purpose — a misconfiguration that would make the transaction form unusable. This is enforced both server-side and client-side (`settings.js`).

4. **`truncate_data` confirmation text.** Case-sensitive exact-match `'TRUNCATE'` confirmation with a visible `<code>TRUNCATE</code>` prompt in the template is the correct pattern.

5. **`simulate_orex_run` parameter clamping.** `count = max(1, min(int(...), 500))` and `delay = max(0, min(int(...), 60))` prevent integer overflow or excessively long simulations from malformed POST values.

6. **Group/squadron rename uses `transaction.atomic()`.** The rename operation wraps `Personnel.objects.update()` + `group.save()` in a single atomic block, preventing a state where the group is renamed but personnel records still hold the old group name.

7. **No `innerHTML` in `settings.js`.** The JS file uses only `style`, `display`, `value`, `textContent`, and DOM API methods — no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval`, or `document.write`. No XSS vectors.

8. **`SystemSettings` cache invalidation.** `save()` correctly deletes the 60-second cache key immediately after the DB write, so settings changes are reflected in the next request.

---

## Fixes Priority Order

| Priority | Finding | Estimated Effort |
|----------|---------|-----------------|
| 1 | SETT-02: Wrap `truncate_data` in `transaction.atomic()` | 5 min |
| 2 | SETT-01: Add `AuditLog` on settings save | 15 min |
| 3 | SETT-03: Fall back to `getattr(obj, field)` in `_psi_fields` loop | 5 min |
| 4 | SETT-04: Fix DB size query for PostgreSQL | 15 min |
| 5 | SETT-05: Add `select_for_update()` to OREX run guard | 10 min |
| 6 | SETT-06: Use `rsplit('_', maxsplit=1)` for orphan cleanup | 2 min |
| 7 | SETT-07: Move stale-expiry to POST endpoint | 20 min |
| 8 | SETT-08: Add `@login_required` to storage endpoints | 2 min |
