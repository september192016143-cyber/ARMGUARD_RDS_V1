# ArmGuard — Transaction Process Audit Report
**Scope:** Transaction creation, saving pipeline, log management, and all related subsystems  
**Files reviewed:** `transactions/views.py`, `transactions/models.py`, `transactions/services.py`, `transactions/forms.py`  
**Classification:** Internal Security & Code Quality Review

---

## Table of Contents
1. [Structural Analysis](#1-structural-analysis)
2. [Bug & Error Detection](#2-bug--error-detection)
3. [Security & Loophole Review](#3-security--loophole-review)
4. [Dependency & Environment Audit](#4-dependency--environment-audit)
5. [Recommendations](#5-recommendations)
6. [Severity Summary Matrix](#6-severity-summary-matrix)

---

## 1. Structural Analysis

### 1.1 Transaction Data Flow

```
HTTP POST /transactions/create/
    │
    ├─ @login_required
    ├─ @ratelimit(rate='auto', methods=['POST'])
    ├─ _can_create_transaction(user)
    │
    ├─ WithdrawalReturnTransactionForm(request.POST, request.FILES)
    │   └─ TransactionAdminForm.clean()  (~750 lines)
    │       ├─ Auto-fill: Duty Sentinel loadout (Glock 17 9mm)
    │       ├─ Auto-fill: Duty Security loadout (caliber-aware rifle)
    │       ├─ Auto-fill: per-purpose magazine, ammo, accessory pools
    │       ├─ Withdrawal validation: firearm availability, qty checks,
    │       │   caliber compatibility, accessory pool caps
    │       ├─ Return validation: ownership, binding rule (all unreturned
    │       │   consumables must accompany the firearm), qty ≤ withdrawn
    │       └─ _post_clean(): sets _validated_from_form=True on instance
    │
    ├─ txn.save(user=request.user)
    │   ├─ propagate_issuance_type()
    │   ├─ Auto-set return_by (TR withdrawals)
    │   └─ db_transaction.atomic()
    │       ├─ [PostgreSQL only] select_for_update() on all locked rows
    │       ├─ [PostgreSQL only] Post-lock re-validation (M-12b)
    │       ├─ super().save()  → INSERT Transaction row
    │       ├─ sync_personnel_and_items()
    │       ├─ adjust_consumable_quantities()
    │       ├─ create_withdrawal_log()  OR  update_return_logs()
    │       └─ write_audit_entry()
    │
    ├─ Cache invalidation: dashboard_stats_{today}, dashboard_cards_{today},
    │   dashboard_inventory_tables
    ├─ [Optional] FirearmDiscrepancy record creation
    └─ Redirect → transaction-detail
```

### 1.2 Module Responsibilities

| Module | Responsibility | Lines (approx.) |
|--------|---------------|-----------------|
| `views.py` | HTTP boundary, auth, rate limiting, cache, routing | ~850 |
| `forms.py` | Input validation, auto-fill, business rule pre-check | ~750 |
| `models.py` | Data model, `clean()` business rules, atomic save orchestration | ~1,350 |
| `services.py` | Side-effect functions (log creation, status sync, audit) | ~550 |

**Design Verdict:** The four-layer separation is architecturally sound. `services.py` was correctly extracted from the original god-object `Transaction.save()`. Each function has a single, documented responsibility and is independently testable.

### 1.3 TransactionLogs Schema Design

`TransactionLogs` is a deliberately **denormalized flat table** (~80 columns) that pairs the withdrawal and return events for all 10 item types into a single row. The design rationale is to avoid costly JOINs when computing log status and to support the binding-rule enforcement (all consumables issued with a firearm are tracked together on one row).

**Trade-offs:**

| Benefit | Cost |
|---------|------|
| Single-query log status calculation | 80-column table — DDL migrations are expensive |
| Binding rule enforced per-row (pistol + all its consumables share one log) | Adding a new item type requires 6–10 new columns + migration |
| No JOIN required to fetch full transaction history | ORM queries are verbose; typos in field names fail at runtime, not compile time |
| Direct `issuance_type` column avoids correlated subquery | Redundant data (issuance_type stored on both Transaction and TransactionLogs) |

### 1.4 Service Layer Analysis

All six service functions in `services.py` are called exclusively from within the `db_transaction.atomic()` block in `Transaction.save()`. They operate as a pipeline:

1. **`propagate_issuance_type`** — copies `issuance_type` to Return records before INSERT. Correct for weapon-based and accessories-only returns. Falls back to most-recent Withdrawal for personnel when no specific log row matches.
2. **`sync_personnel_and_items`** — updates Personnel issued-status fields and Pistol/Rifle `item_issued_to_id`. Correctly clears all 10 item types on Return. Runs after `super().save()` so `transaction.pk` is set.
3. **`adjust_consumable_quantities`** — calls `adjust_quantity(delta)` on Magazine, Ammunition, and Accessory pools. Uses `sign = -1` for Withdrawal and `+1` for Return. Skips if quantity field is None/0.
4. **`create_withdrawal_log`** — creates one TransactionLogs row. Correctly handles three cases: pistol+rifle (combined row), pistol-only, rifle-only, and consumable-only (standalone row). Username is stamped directly in this function, not delegated to `TransactionLogs.save()`.
5. **`update_return_logs`** — finds each item's open log row, accumulates mutations in `logs_to_save` dict (keyed by `record_id`), then persists once per row. The accumulation pattern is critical for combined pistol+rifle log rows — ensures both weapon returns are written to the same DB row.
6. **`write_audit_entry`** — structured `INFO`-level log entry. Immutable once written.

---

## 2. Bug & Error Detection

### B-1 — CRITICAL: No Row-Level Locking on SQLite (TOCTOU Race)
**Location:** `models.py` — `Transaction.save()`, `services.py` — `update_return_logs()`  
**Severity:** Critical (data integrity)  

```python
# models.py — lock guard is silently skipped on SQLite
from django.db import connection as _conn
if _conn.vendor != 'sqlite':
    pistol_qs = pistol_qs.select_for_update()
```

`select_for_update()` is a no-op on SQLite. SQLite uses database-level write locks (WAL mode), not row-level locks. Under Gunicorn with multiple workers, two concurrent Withdrawal requests for the same pistol can both pass `can_be_withdrawn()` before either worker reaches `super().save()`. Both writes succeed. The same physical firearm is recorded as issued to two different personnel simultaneously.

The `update_return_logs()` function in `services.py` has the same guard:
```python
def _lock(qs):
    return qs.select_for_update() if _conn.vendor != 'sqlite' else qs
```

**Impact:** Duplicate issuance of the same weapon is possible in a multi-worker production environment running SQLite. This is the most critical data integrity gap in the system.

**Fix:** Migrate to PostgreSQL. Until then, set `workers = 1` in `gunicorn.conf.py` to enforce single-worker operation. This prevents concurrency but eliminates the race condition.

---

### B-2 — HIGH: Accessory Pool Selection Inconsistency (Three Different Queries)
**Location:** `forms.py`, `models.py` (`clean()`), `services.py` (`adjust_consumable_quantities`)  
**Severity:** High (inventory integrity on multi-pool setups)  

Three code paths select an accessory pool using different queries:

| Location | Query |
|----------|-------|
| `forms.py` availability check | `Accessory.objects.filter(type=acc_label).first()` (no ordering) |
| `models.py` `clean()` pool check | `Accessory.objects.filter(type=acc_type).order_by('-quantity').first()` |
| `services.py` `adjust_consumable_quantities` | `Accessory.objects.filter(type=acc_type).order_by('-quantity').first()` |

If there are multiple `Accessory` pool records of the same type (e.g., two separate "Pistol Holster" entries), `forms.py` validates availability against an arbitrary pool (whichever `.first()` returns) while `services.py` deducts from the highest-quantity pool. This could produce:
- A validation pass against a depleted pool followed by a deduction from a different pool
- Inventory skew when accessories are returned — `adjust_consumable_quantities` restores quantity to the highest-quantity pool, not necessarily the one that was originally depleted

**Fix:** Standardize all three queries to use `Accessory.objects.filter(type=acc_type).order_by('-quantity').first()`. Consider adding a `UniqueConstraint` on `Accessory.type` to prevent multi-pool duplicates, or explicitly document that one pool per accessory type is required.

---

### B-3 — MEDIUM: Ammunition Auto-Fill Uses Unordered `.first()` Query
**Location:** `forms.py` — auto-fill logic for pistol/rifle ammunition  
**Severity:** Medium (form UX, potential validation failure)  

Magazine and accessory auto-fill queries correctly use `.order_by('-quantity')` to select the most stocked pool. Ammunition auto-fill does not:

```python
# forms.py — magazine (correct, ordered)
mag_pool = Magazine.objects.filter(weapon_type='Pistol', ...).order_by('-quantity').first()

# forms.py — ammo (missing order_by)
ammo_pool = Ammunition.objects.filter(type=ammo_type).first()  # arbitrary selection
```

If multiple `Ammunition` records exist for the same type, the form may auto-select a depleted pool, causing the subsequent `can_be_withdrawn(qty)` validation to fail with "Insufficient stock" even when adequate stock exists in another pool.

**Fix:**
```python
ammo_pool = Ammunition.objects.filter(type=ammo_type).order_by('-quantity').first()
```

---

### B-4 — MEDIUM: Accessory Quantities Missing from Audit Log
**Location:** `services.py` — `write_audit_entry()`  
**Severity:** Medium (audit trail completeness)  

```python
def write_audit_entry(transaction, username):
    items = []
    if transaction.pistol:      items.append(f"Pistol {transaction.pistol.item_id}")
    if transaction.rifle:       items.append(f"Rifle {transaction.rifle.item_id}")
    if transaction.pistol_magazine:   items.append(f"Pistol Mag x{transaction.pistol_magazine_quantity}")
    if transaction.rifle_magazine:    items.append(f"Rifle Mag x{transaction.rifle_magazine_quantity}")
    if transaction.pistol_ammunition: items.append(f"Pistol Ammo x{transaction.pistol_ammunition_quantity}")
    if transaction.rifle_ammunition:  items.append(f"Rifle Ammo x{transaction.rifle_ammunition_quantity}")
    # ← Holster, Magazine Pouch, Rifle Sling, Bandoleer quantities are NOT logged
```

Transactions involving only accessories (e.g., a Bandoleer return) produce an audit log entry with `items=accessories` — no quantities recorded. Transactions that include accessories alongside weapons log the weapon details but silently omit the accessory counts.

**Fix:** Add accessory items to the `items` list:
```python
if transaction.pistol_holster_quantity:
    items.append(f"Holster x{transaction.pistol_holster_quantity}")
if transaction.magazine_pouch_quantity:
    items.append(f"Mag Pouch x{transaction.magazine_pouch_quantity}")
if transaction.rifle_sling_quantity:
    items.append(f"Rifle Sling x{transaction.rifle_sling_quantity}")
if transaction.bandoleer_quantity:
    items.append(f"Bandoleer x{transaction.bandoleer_quantity}")
```

---

### B-5 — LOW: Discrepancy Image Validation Silently Discards Invalid Images
**Location:** `views.py` — `create_transaction()`, `_validate_discrepancy_image()`  
**Severity:** Low (operator UX, silent data loss)  

`_validate_discrepancy_image()` returns `None` on any failure (Pillow verify error, wrong format, file too large) without raising or returning an error message. The caller:

```python
img_bytes = _validate_discrepancy_image(f)
if img_bytes is not None:
    FirearmDiscrepancy.objects.create(image=img_bytes, ...)
# No else: — operator gets no feedback if image was rejected
```

An operator who uploads a malformed or oversized discrepancy image receives no error message. The transaction is saved successfully (as intended — discrepancy image must never block a Return), but the image is silently dropped. The operator may believe the discrepancy was recorded when it was not.

**Fix:** Return an error code or message from `_validate_discrepancy_image()` and surface it as a non-blocking warning in the transaction success response or detail page.

---

### B-6 — LOW: `propagate_issuance_type` May Select Wrong Issuance for Multi-Cycle Personnel
**Location:** `services.py` — `propagate_issuance_type()`  
**Severity:** Low (edge case, only affects accessories-only returns)  

For accessories-only returns with no pistol or rifle, the function walks through consumable types (mag → ammo → holster → pouch → sling → bandoleer) and uses the open `TransactionLogs` row of the first matching type to resolve `issuance_type`. If none match, it falls back to the most-recent Withdrawal for the personnel.

This fallback is not type-specific. In the unlikely scenario where a personnel has an open PAR cycle for a rifle and a separate TR cycle for a standalone holster (without a firearm), the fallback may assign PAR as the issuance type for the TR return. In practice, the binding rule prevents firearm and accessory cycles from being interleaved, but this edge case exists for accessories-only issuances.

**No immediate fix required** — the specific-log lookup handles the normal case correctly; the fallback is a best-effort approximation for unusual configurations.

---

## 3. Security & Loophole Review

### S-1 — CRITICAL: Concurrent Duplicate Issuance on SQLite
*(See B-1 above — also a security concern for asset accountability)*

An insider or network attacker who can trigger simultaneous form submissions (e.g., double-click, two browser tabs, or a scripted request) can cause the same weapon to be recorded as issued to two different personnel. This undermines physical asset accountability.

**Mitigation until PostgreSQL:** Set `workers = 1` in `gunicorn.conf.py`.

---

### S-2 — HIGH: Session Cookies Not Secure by Default
**Location:** `.env` / `settings/production.py`  
**Severity:** High (session hijacking risk)  

`SECURE_SSL_REDIRECT=False` by default means `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are also effectively `False` unless explicitly overridden in `.env`. Session tokens sent over plain HTTP can be intercepted on the LAN.

**Fix in `.env`:**
```
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
```

---

### S-3 — HIGH: FileBasedCache Rate Limiter Not Race-Safe Under Multi-Worker Load
**Location:** `armguard/settings/` — `CACHES` configuration  
**Severity:** High (rate limiter bypassed under concurrent load)  

`django-ratelimit` uses `cache.add()` / `cache.incr()` for its counting mechanism. With `FileBasedCache`, these operations are not atomic — two Gunicorn workers can simultaneously read a counter below the limit and both increment past it before either write is persisted. Under load, the effective rate limit is higher than configured.

**Fix:** Switch to Redis cache (`django-redis`). Redis `INCR` is atomic. Update `CACHES` in `settings/production.py`:
```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    }
}
```

---

### S-4 — MEDIUM: `personnel_status` and `item_status_check` Have No Rate Limit
**Location:** `views.py`  
**Severity:** Medium (insider enumeration risk)  

Both endpoints return sensitive operational data: which weapons are issued to which personnel, current item availability with serial numbers, and ID card URLs. They are intentionally rate-limit-free to avoid breaking the transaction form UX. However, an authenticated insider can script rapid queries to enumerate the entire personnel + weapon assignment database.

**Mitigations:**
- Apply nginx `limit_req` rate limiting at the proxy layer (e.g., 30 req/s per IP, 60 req/s burst) — this does not interfere with Django's AJAX response path.
- Consider adding `X-RateLimit` headers via middleware for monitoring.

---

### S-5 — MEDIUM: `tr_preview` Bypasses Business Rule Validation
**Location:** `views.py` — `tr_preview()`  
**Severity:** Medium (low data risk, operator misguidance risk)  

`tr_preview` builds a `mock_txn` using `SimpleNamespace` from raw form data, calls `TransactionFormFiller.fill_transaction_form()`, and returns a PDF. The `mock_txn` is not a real Django model instance and does not go through `Transaction.clean()` or `forms.py` validation. A carefully crafted POST to `/transactions/preview/` can generate a TR PDF for a transaction configuration that would fail validation on actual save (wrong issuance type, over-quantity ammo, etc.).

No data is saved. The risk is that a preview PDF could mislead an operator or be used to create a false paper record without corresponding database entries.

**Mitigations:**
- Run the form's `is_valid()` check before generating the preview and return form errors if validation fails.
- Watermark the preview PDF prominently (e.g., "DRAFT — NOT OFFICIAL") — verify the current watermark implementation covers all preview PDFs.

---

### S-6 — MEDIUM: PAR Document Upload — Filename Sanitization Does Not Block Path Components
**Location:** `models.py` — `_sanitize_par_upload()`  
**Severity:** Medium (path traversal partially mitigated)  

`_sanitize_par_upload` applies NFKD normalization, strips non-ASCII characters, and replaces spaces. It does not explicitly strip `../`, `./`, or path separators from the filename. Django's `FileField` with `upload_to` callable generates the final storage path from the upload directory + sanitized filename. While Django's file storage backends do normalize paths before writing, the absence of an explicit `os.path.basename()` call leaves a narrow window for path injection via Unicode path-separator substitution.

**Fix:** Add a final `os.path.basename()` call at the end of `_sanitize_par_upload`:
```python
import os
sanitized = os.path.basename(sanitized)
```

---

### S-7 — LOW: `build_absolute_uri` May Return HTTP URLs When SSL Not Enforced
**Location:** `views.py` — `personnel_status()`, `item_status_check()`  
**Severity:** Low (URL disclosure, links to sensitive images over HTTP)  

```python
data['id_card_front_url'] = request.build_absolute_uri(_settings.MEDIA_URL + front_rel)
data['item_tag_url'] = request.build_absolute_uri(item.item_tag.url)
data['serial_image_url'] = request.build_absolute_uri(item.serial_image.url)
```

When `SECURE_SSL_REDIRECT=False` (the current default), these URLs will use `http://` if the request arrived over HTTP. ID card images, item ID tags, and serial number photographs are sensitive and should only be served over HTTPS. This compounds S-2.

**Fix:** Enforce HTTPS via `SECURE_SSL_REDIRECT=True` (see S-2) and set `USE_X_FORWARDED_HOST = True` + `SECURE_PROXY_SSL_HEADER` if behind nginx.

---

### S-8 — LOW: Double-Submit Protection Missing on Transaction Form
**Location:** `views.py` — `create_transaction()`  
**Severity:** Low (UX, potential duplicate records)  

There is no server-side idempotency token or client-side submit-once guard documented on the transaction form. The rate limiter (`rate='auto'`) applies per-user burst limits but does not prevent a legitimate double-click or form resubmission from creating two identical transaction records (e.g., two Withdrawal rows for the same weapon, where the second fails at the `can_be_withdrawn()` check — but only if SQLite's non-atomic lock doesn't cause both to succeed).

**Fix:** Add a CSRF-based one-time form token or a client-side `data-loading` attribute that disables the submit button after first click.

---

### S-9 — INFORMATIONAL: `purpose` Field Accepts Freeform Text Beyond Allowlist
**Location:** `models.py`, `forms.py`  
**Severity:** Informational  

The `purpose` field has no `choices` constraint at the database level. The `CheckConstraint` was removed in migration 0006. The form uses a `CharField` with a `Select` widget, but the widget is not enforced server-side — a raw POST can submit any string. `Transaction.clean()` validates against `PURPOSE_CHOICES` OR permits freeform text when `purpose_other` is set. This is intentional (to support the "Others" purpose with custom text), but it means the `purpose` field in the database can contain arbitrary strings if the admin bypasses the form.

**Note:** Admin access already requires authentication + OTP + administrator role, so this is a low-privilege risk.

---

## 4. Dependency & Environment Audit

### 4.1 Database

| Item | Current | Recommended | Risk |
|------|---------|-------------|------|
| Engine | **SQLite** | PostgreSQL 15+ | Critical — no row-level locks, single-writer WAL |
| `psycopg2-binary` | Commented out in `requirements.txt` | Install when migrating | Migration blocker |
| `CONN_MAX_AGE` | 600 | Keep | Appropriate for long-lived workers |
| `CONN_HEALTH_CHECKS` | True | Keep | Prevents stale connection errors |

**Migration path:** Follow `scripts/DEPLOY_GUIDE.md`. After migration, remove the `_conn.vendor != 'sqlite'` guards from `models.py` and `services.py`.

### 4.2 Cache

| Item | Current | Recommended | Risk |
|------|---------|-------------|------|
| Backend | `FileBasedCache` | `django-redis` | High — rate limiter not atomic |
| Cache keys | `dashboard_stats_{today}`, `dashboard_cards_{today}`, `dashboard_inventory_tables` | No change needed | Low TTLs (10–60s) limit stale-data window |
| Rate limiter | `django-ratelimit` + FileBasedCache | Same lib + Redis backend | High — see S-3 |

### 4.3 Web Server / Proxy

| Item | Current | Recommended | Risk |
|------|---------|-------------|------|
| WSGI server | `gunicorn==22.0.0` | Keep | Current, no known CVEs |
| Workers | Configured in `gunicorn.conf.py` | **Set to 1 until PostgreSQL** | Critical — SQLite + multi-worker = race condition |
| Proxy | nginx (per `scripts/`) | Keep | No issues found |
| SSL | Self-signed (LAN) | Keep for LAN + enforce redirect | Medium — see S-2 |

### 4.4 Key Pinned Dependencies

| Package | Version | Notes |
|---------|---------|-------|
| Django | 6.0.3 | Very recent; pinned — good |
| Pillow | 12.1.1 | Current; used for image validation |
| PyMuPDF | 1.27.1 | Current; PDF generation |
| django-otp | 1.7.0 | TOTP MFA — current |
| djangorestframework | 3.16.0 | Current |
| openpyxl | 3.1.5 | Current |
| whitenoise | 6.12.0 | Current |
| qrcode | 8.2 | Current |

No known critical CVEs found in pinned versions as of review date. Keep `requirements.txt` pinned; schedule a quarterly dependency update review.

### 4.5 Pending Server Action (BLOCKING)

Migration `transactions/0006` creates a duplicate index on the production server. The server cannot run new migrations until this is resolved:

```bash
cd /var/www/ARMGUARD_RDS_V1/project
export DJANGO_SETTINGS_MODULE=armguard.settings.production
python manage.py migrate transactions 0006 --fake
python manage.py migrate --check
```

Then pull the latest commits and restart Gunicorn:
```bash
git pull origin main
sudo systemctl restart armguard-gunicorn
```

---

## 5. Recommendations

### Priority 1 — Immediate (Before Next Deployment)

**R1.1 Set Gunicorn workers = 1 until PostgreSQL migration**  
File: `scripts/gunicorn.conf.py`  
```python
workers = 1  # SQLite is single-writer; multi-worker creates TOCTOU race on withdrawals
```
This reduces throughput but eliminates the duplicate-issuance race condition.

**R1.2 Run the pending migration on the production server**  
See Section 4.5. The server is currently in a broken migration state that blocks future schema changes.

**R1.3 Enforce HTTPS cookies in `.env`**  
```
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

---

### Priority 2 — Short-Term (Next Sprint)

**R2.1 Fix ammunition auto-fill to use ordered query**  
File: `forms.py`  
Change all `Ammunition.objects.filter(type=ammo_type).first()` to `.order_by('-quantity').first()` — three locations in the auto-fill block.

**R2.2 Add accessory quantities to audit log**  
File: `services.py` — `write_audit_entry()`  
Add 4 lines as shown in B-4. Every transaction must be fully represented in the audit trail.

**R2.3 Add `os.path.basename()` to `_sanitize_par_upload`**  
File: `models.py`  
```python
import os
# At the end of _sanitize_par_upload:
return os.path.basename(sanitized)
```

**R2.4 Surface discrepancy image validation failures**  
File: `views.py`  
When `_validate_discrepancy_image()` returns `None`, add the image filename and reason to the session messages so the transaction success page warns the operator.

---

### Priority 3 — Medium-Term (Infrastructure Sprint)

**R3.1 Migrate to PostgreSQL**  
This is the single most impactful change: enables row-level locking, removes the TOCTOU race condition on withdrawals, enables `select_for_update()` in `models.py` and `services.py`, and unblocks multi-worker Gunicorn deployment. Follow `scripts/DEPLOY_GUIDE.md`.

After migration, remove all `_conn.vendor != 'sqlite'` guards:
```python
# models.py and services.py — remove this pattern entirely:
if _conn.vendor != 'sqlite':
    qs = qs.select_for_update()
```

**R3.2 Switch to Redis cache**  
Install `django-redis` and update `CACHES` in `settings/production.py` (see S-3). This makes rate limiting atomic and allows `cache.add()` to work correctly under multi-worker load.

**R3.3 Add nginx rate limiting for `personnel_status` and `item_status_check`**  
In `nginx-armguard.conf`:
```nginx
limit_req_zone $binary_remote_addr zone=ajax_status:10m rate=30r/s;

location /transactions/personnel-status/ {
    limit_req zone=ajax_status burst=60 nodelay;
    proxy_pass http://armguard_app;
}
location /transactions/item-status/ {
    limit_req zone=ajax_status burst=60 nodelay;
    proxy_pass http://armguard_app;
}
```
This protects enumeration without disrupting the Django-level form UX.

---

### Priority 4 — Long-Term (Architectural)

**R4.1 Normalize TransactionLogs schema**  
The 80-column flat table works but is a maintenance liability. Consider a `TransactionLogItem` model with a FK to `TransactionLog` and `item_type` + `item_pk` (generic FK or typed FK). This would:
- Reduce column count from ~80 to ~15
- Enable adding new item types without migrations
- Make ORM queries shorter and less error-prone

This is a significant data migration and should be planned carefully with a full backup and tested migration script.

**R4.2 Add idempotency token to transaction form**  
Add a hidden `submission_token` (UUID, generated server-side, stored in session, consumed on first use) to prevent double-submit from creating duplicate transactions. This is a standard Django pattern:
```python
# In the view: generate and store token
# In the form: submit with token
# On POST: check and consume token before processing
```

**R4.3 Standardize accessory pool selection**  
Add a `UniqueConstraint` on `Accessory.type` in the Accessory model, or document that only one pool per accessory type is supported. This eliminates the three-query inconsistency described in B-2.

---

## 6. Severity Summary Matrix

| ID | Description | Severity | Category | Status |
|----|-------------|----------|----------|--------|
| B-1 / S-1 | No row-level locking on SQLite — TOCTOU race on concurrent withdrawals | **Critical** | Bug + Security | Open |
| S-2 | Session/CSRF cookies not Secure by default | **High** | Security | Open |
| S-3 | FileBasedCache rate limiter not atomic under multi-worker load | **High** | Security | Open |
| B-2 | Accessory pool selection uses three different queries | **High** | Bug | Open |
| B-3 | Ammunition auto-fill uses unordered `.first()` | **Medium** | Bug | Open |
| B-4 | Accessory quantities missing from audit log | **Medium** | Bug | Open |
| S-4 | `personnel_status`/`item_status_check` have no rate limit | **Medium** | Security | Open (intentional) |
| S-5 | `tr_preview` bypasses business rule validation | **Medium** | Security | Open |
| S-6 | PAR upload sanitizer lacks `os.path.basename()` | **Medium** | Security | Open |
| B-5 | Discrepancy image rejection is silent — no operator feedback | **Low** | Bug | Open |
| B-6 | `propagate_issuance_type` fallback may select wrong issuance | **Low** | Bug | Edge case |
| S-7 | `build_absolute_uri` returns HTTP URLs when SSL not enforced | **Low** | Security | Blocked on S-2 |
| S-8 | No double-submit protection on transaction form | **Low** | Security | Open |
| S-9 | `purpose` field accepts freeform text beyond allowlist | **Info** | Security | By design |
| — | `migrate transactions 0006 --fake` pending on production | **Blocking** | Ops | **Must run now** |

---

*Report generated by code review. All findings are based on static analysis of the current codebase. Dynamic testing (penetration testing, load testing) is recommended to validate concurrency findings under production conditions.*
