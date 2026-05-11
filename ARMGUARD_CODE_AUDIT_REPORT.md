# ARMGUARD RDS V1 — Full Code Review Report

**Date:** 2026 (Post-remediation, pre-release review)
**Version:** ARMGUARD_RDS_V1 — commit `eaf5e88`
**Reviewer:** GitHub Copilot (Claude Sonnet 4.6)
**Scope:** 128 Python source files, 58 HTML templates, 34 JS files, CI pipeline, Nginx/Gunicorn deployment scripts

---

## Overall Verdict

| Section | Score |
|---|---|
| 1. Project & Folder Structure | 8/10 |
| 2. Architecture & Design Patterns | 7/10 |
| 3. Code Quality | 8/10 |
| 4. Security | 8/10 |
| 5. Performance | 7/10 |
| 6. Testing & Reliability | 8/10 |
| 7. Dependencies & Environment | 7/10 |
| **Composite** | **7.6/10** |

---

## 1. Project & Folder Structure

### Strengths
- Clean Django project layout: `project/armguard/` root with all apps under `apps/`, shared utils under `armguard/utils/`, middleware under `armguard/middleware/`.
- Settings split correctly into `base.py`, `development.py`, `production.py`. `manage.py` defaults to development; production requires explicit `DJANGO_SETTINGS_MODULE`.
- Deployment artifacts separated cleanly: `scripts/` for shell scripts, `fonts/`, `card_templates/` for print assets.
- Per-app URL modules included from root `urls.py` — correct Django pattern.
- `robots.txt` and `security.txt` served as templates at well-known paths — good.

### Findings

**STR-01** — `project/armguard/apps/users/` — No `forms.py` exists; `UserCreateForm` and `UserUpdateForm` are both defined at the top of `views.py`. Every other app (`inventory`, `personnel`, `transactions`, `camera`) has a `forms.py`. Fix: extract both form classes to a new `users/forms.py`.

**STR-02** — `.github/workflows/ci.yml:23` — `working-directory: final/ARMGUARD_RDS_V1/project` is a hardcoded path that does not match the actual workspace folder (`final.1`). Same wrong path used for `pip install -r armguard/requirements.txt` (line ~45) and the Docker build context (`context: final/ARMGUARD_RDS_V1`). CI pipeline **will not run** on any clone of the real repository. Fix: use `${{ github.workspace }}/project` or a relative path that matches the repo root.

**Verdict: 8/10** — Well-structured overall; deducted for no `forms.py` in the users app and the broken CI path.

---

## 2. Architecture & Design Patterns

### Strengths
- Permission layer centralised in `armguard/utils/permissions.py` — 14 granular helpers, all following the same priority chain (superuser → System Administrator → Administrator → Armorer → deny). No scattered `is_staff` checks in views.
- Service layer extracted from `Transaction.save()` into `transactions/services.py` (C6 FIX): `propagate_issuance_type`, `sync_personnel_and_items`, `adjust_consumable_quantities`, `create_withdrawal_log`, `update_return_logs`, `write_audit_entry` — correct single-responsibility extraction.
- Camera authentication is self-contained: HMAC rotating key in `camera/models.py`, session management in `camera/views.py`, no coupling to main login system.
- `OTPRequiredMiddleware` enforces MFA fail-CLOSED: DB errors redirect to OTP verify, never silently pass.
- `SingleSessionMiddleware` correctly compares `profile.last_session_key` to `request.session.session_key` to invalidate old sessions.

### Findings

**ARCH-01** — `armguard/apps/users/views.py` — 1,703 lines. The file contains two form classes, eight CBV classes, ~15 FBV views, OTP setup/verify, OREX simulation logic, and storage analytics helpers. Django convention is one concern per module. Fix: split into `users/forms.py`, `users/views/settings.py`, `users/views/otp.py`, `users/views/simulation.py`, keeping the main `views.py` as an import relay.

**ARCH-02** — `armguard/apps/transactions/models.py:Transaction.clean()` — approximately 400 lines implementing business rules for 10 item types × 2 transaction types. While the logic itself is correct and well-tested, the method length makes future maintenance error-prone. Fix: extract ammo/magazine compatibility checks into `_validate_ammo_compatibility()`, `_validate_magazine_compatibility()`, and return/binding rules into `_validate_return()` helper functions within the same module.

**ARCH-03** — `armguard/apps/transactions/signals.py:on_transaction_save` + `armguard/apps/transactions/services.py:write_audit_entry` — both write an `AuditLog` row on every `Transaction.save()`. Every new transaction creates **two** `AuditLog` entries with identical data. Fix: remove `_write_audit_log()` from `signals.py:on_transaction_save` (keep the one in `services.py` which runs inside the `atomic()` block).

**ARCH-04** — `armguard/apps/users/views.py:simulate_orex_run` — launches `threading.Thread(daemon=False)` with no thread pool and no hard concurrency cap. A `SimulationRun` DB guard prevents double-start under normal conditions, but a concurrent request race between the DB check and `thread.start()` could trigger two threads. Low risk in practice (admin-only feature), but should use `daemon=True` so the thread does not prevent interpreter shutdown.

**Verdict: 7/10** — Good architectural intent; deducted for monolithic `views.py`, double audit logging, and overly long `clean()`.

---

## 3. Code Quality

### Strengths
- Consistent permission-check pattern across all CBVs: `LoginRequiredMixin` + `UserPassesTestMixin` with `test_func()` delegating to `armguard/utils/permissions.py`.
- `_InventoryPermMixin` / `_InventorySaveMixin` base classes in `inventory/views.py` eliminate repetition across 5 inventory types.
- Type annotations on `permissions.py` helper return types (`-> bool`, `-> str`).
- Logging via `logging.getLogger(__name__)` in views — not bare `print()`.
- `AuditLog.save()` uses `update()` (not recursive `save()`) to store the integrity hash — correct.
- `factories.py` in tests uses `_pid_counter` to auto-generate unique IDs — prevents test isolation failures.

### Findings

**QUAL-01** — `armguard/apps/users/views.py:SystemSettingsView.post()` — The method handles ~50 settings fields inline in one `if request.method == 'POST':` block. There is no ModelForm validation before saving raw string values from `request.POST.get(...)` to model fields. Fix: use a `ModelForm` for `SystemSettings` or add explicit field-by-field validation before each `setattr()`.

**QUAL-02** — `armguard/apps/inventory/views.py:PistolListView.render_to_response()` — AJAX detection uses `X-Requested-With: XMLHttpRequest` header. This non-standard header is not sent by modern `fetch()` calls. Fix: use a dedicated `?format=partial` query param or a JSON-mode URL, and document the convention.

**QUAL-03** — `armguard/apps/dashboard/views.py` — `_NOMENCLATURE` and `_MODEL_ORDER` dicts are module-level constants duplicated from comments in `inventory/models.py`. A single source of truth in `inventory/models.py` and an import in `dashboard/views.py` would eliminate the duplication risk.

**QUAL-04** — `armguard/apps/camera/admin.py:27-30` — uses bare `mark_safe()` with static HTML strings. While the strings contain no user data, `format_html()` is the canonical safe pattern even for static markup. No security risk, but violates the convention established elsewhere in the codebase.

**Verdict: 8/10** — Code is clean and consistent; deducted for the 50-field inline settings POST handler and the AJAX detection pattern.

---

## 4. Security

### Strengths
- **MFA**: `OTPRequiredMiddleware` enforces TOTP for all authenticated routes. Fail-CLOSED (DB error → deny). Per-user and site-wide toggle via `SystemSettings`. API bypass for `Token`/`Bearer` headers only — correct.
- **CSP**: `ContentSecurityPolicyMiddleware` applies on `text/html` responses only. No `unsafe-eval`. `frame-ancestors 'none'`, `object-src 'none'`. `style-src` retains `'unsafe-inline'` for Django admin — documented, acceptable.
- **Audit trail**: SHA-256 integrity hash on every `AuditLog` row. Tamper detection via `verify_integrity()`.
- **Rate limiting**: Login endpoint protected at 5 POST/min via custom `ratelimit` decorator. API token endpoint throttled at 5/min via `_TokenAuthThrottle`. PII API endpoints throttled at 60/hour.
- **File upload security**: All upload handlers validate extension + Pillow magic-byte check. UUID-based filenames — no client-supplied names written to disk. PDF uploads additionally check `%PDF` magic bytes.
- **Password storage**: `PasswordHistory` stores hashes only, never plaintext. `DynamicMinLengthValidator` + `PasswordHistoryValidator` enforced at DB level.
- **HMAC camera key**: 256-bit `device_token`, HMAC-SHA256 rotating per 5-minute window, constant-time comparison via `hmac.compare_digest()`.
- **Admin URL obscured**: `ADMIN_URL` read from env var — correct defense-in-depth.
- **Single-session enforcement**: `SingleSessionMiddleware` invalidates the old session on new login.

### Findings

**SEC-01** — `armguard/apps/camera/views.py:_client_ip()` — uses `xff.split(',')[0].strip()` (the **first** entry in `X-Forwarded-For`, which is client-controlled and trivially spoofed). Every other module (`middleware/activity.py`, `apps/users/models.py`) correctly uses `split(',')[-1].strip()` (the **last** entry, appended by Nginx and therefore trusted). Camera audit logs (`CameraUploadLog.ip_address`) can be forged with a spoofed `X-Forwarded-For` header. Fix: change `[0]` to `[-1]` in `_client_ip()` in `camera/views.py`.

**SEC-02** — `armguard/templates/registration/login.html:8-9` — loads FontAwesome from `cdnjs.cloudflare.com` (CDN) **and** from `{% static 'css/fontawesome/all.min.css' %}` (self-hosted). The CDN load has no `integrity=` Subresource Integrity attribute. If the CDN is compromised, arbitrary CSS could be injected. Since the self-hosted copy is also loaded, the CDN load is redundant. Fix: remove the CDN `<link>` tag; serve FontAwesome entirely from WhiteNoise.

**SEC-03** — `project/armguard/settings/base.py:X_FRAME_OPTIONS = 'SAMEORIGIN'` — `XFrameOptionsMiddleware` is not in `MIDDLEWARE`, so this setting has no effect. CSP `frame-ancestors 'none'` is the actual clickjacking protection. The dead setting may create false confidence in a future audit. Fix: remove `X_FRAME_OPTIONS` from `base.py`, or add a comment explaining that CSP `frame-ancestors` supersedes it.

**SEC-04** — `armguard/apps/users/views.py:simulate_orex_run` — the `SimulationRun` concurrency guard performs a `filter().exists()` check then launches a thread. These two operations are not atomic. Under load, two simultaneous requests could both pass the `exists()` check before either creates the DB record. Fix: wrap the guard and record creation in `select_for_update()` inside an `atomic()` block.

**Verdict: 8/10** — Excellent depth of security controls; deducted for the camera IP spoofing bug (SEC-01) and the CDN load without SRI (SEC-02).

---

## 5. Performance

### Strengths
- `dashboard/views.py:_build_inventory_table()` — replaced 10 per-model queries with 2 grouped `annotate()` queries (5.6 FIX).
- `ActivityLog` has 4 composite indexes (`user+timestamp`, `path+method`, `flag+timestamp`, `session_key`).
- `Transaction.save()` uses `select_for_update()` inside `atomic()` to prevent TOCTOU on all involved rows.
- Dashboard stats cached with `cache.set(stats_key, ..., 300)` and invalidated on `Transaction.save()`.
- `PistolListView.get_context_data()` uses a single `aggregate()` for total/available/issued counts instead of 3 queries (M2 FIX).

### Findings

**PERF-01** — `armguard/apps/transactions/views.py:TransactionListView.get_queryset()` — annotates the queryset with 4 correlated subqueries on every list page load (prior withdrawal issuance type, `return_by`, `pistol_returned_ts`, `rifle_returned_ts`). On large datasets without composite index coverage on `(transaction_type, pistol_id, timestamp)` and `(transaction_type, rifle_id, timestamp)`, these subqueries will be slow. Fix: verify `EXPLAIN ANALYZE` on the production dataset; add composite indexes if needed, or denormalize the `issuance_type` / return timestamps onto the return transaction row.

**PERF-02** — `armguard/apps/transactions/models.py:Transaction.clean()` — every `Transaction.save()` acquires row-level locks on up to 4 related objects (pistol, rifle, personnel, accessories) via `select_for_update()`. Under concurrent load this could cause lock contention. No action required unless load testing reveals it; document for future review.

**PERF-03** — `armguard/apps/users/views.py:SystemSettingsView` — reads ~50 settings fields on every GET. `SystemSettings` is a single-row table; the GET path should cache the result with `cache.get_or_set()`. POST path is admin-only and infrequent — no immediate fix required there.

**Verdict: 7/10** — Good caching and aggregation improvements; the correlated subquery list annotation (PERF-01) is the main concern at scale.

---

## 6. Testing & Reliability

### Strengths
- 113 tests, 0 skipped as of commit `eaf5e88`.
- `factories.py` provides `make_user`, `make_admin_user`, `make_personnel`, `make_pistol`, `make_rifle`, `otp_login` — tests do not repeat setup boilerplate.
- `otp_login()` helper correctly force-logs in and sets `_otp_step_done` in session — MFA middleware is exercised by tests.
- `TestTransactionDetailView` tests 404 for nonexistent transaction IDs.
- `TestCreateTransactionPermissions` tests that role `''` (no role) gets 403 — confirms permission layer is enforced.
- `test_auth.py:TestOTPVerifyView.test_wrong_otp_returns_error()` — verifies that a wrong TOTP token does not redirect to dashboard.
- `AuditLog.verify_integrity()` enables runtime tamper detection — testable and documented.

### Findings

**TEST-01** — `.github/workflows/ci.yml` — CI runs `python manage.py test armguard.tests`. This discovers only `armguard/tests/*.py`. Per-app test files (`armguard/apps/*/tests.py`) are **not** discovered or run by CI. Fix: change the test label to `python manage.py test armguard` (no subpath), which discovers all tests under the project.

**TEST-02** — `armguard/tests/test_transactions.py:TestTransactionCacheInvalidation` — the test directly calls `cache.delete()` rather than triggering the actual `Transaction.save()`. It verifies the cache mechanism, not whether the view or signal correctly calls `cache.delete()` after a real save. Fix: replace with an end-to-end test that POSTs a valid transaction via the create view and then asserts the cache key is gone.

**TEST-03** — No tests found for `camera/views.py` upload flow, `middleware/mfa.py` bypass conditions, or `middleware/session.py` single-session invalidation. These are critical security paths. Fix: add integration tests for camera API key rejection, MFA bypass (Token header), and session invalidation on second login.

**Verdict: 8/10** — Solid test foundation with good factories and OTP helpers; deducted for CI not discovering per-app tests and absence of camera/middleware tests.

---

## 7. Dependencies & Environment

### Strengths
- Most dependencies pinned to exact versions (`Django==6.0.3`, `gunicorn==22.0.0`, `pillow==12.1.1`, `django-otp==1.5.4`, `djangorestframework==3.16.0`, `whitenoise==6.9.0`).
- `pip-audit` included in CI pipeline for CVE scanning (when CI path is fixed).
- `psycopg2-binary` used for PostgreSQL — correct for production use.
- Production settings require `SECRET_KEY` and `ALLOWED_HOSTS` via env vars; both raise `ValueError` if absent — correct fail-fast pattern.
- `SECURE_HSTS_SECONDS=31536000` set in `production.py` — full HSTS preload-eligible duration.

### Findings

**DEP-01** — `requirements.txt` — five packages use `>=` (minimum version) instead of exact pins:
- `drf-spectacular>=0.27.0`
- `psycopg2-binary>=2.9.9`
- `redis>=5.0.0`
- `gspread>=6.0.0`
- `google-auth>=2.29.0`

Silent upgrades of these packages could break production on `pip install -r requirements.txt`. Fix: pin all five to exact versions matching the currently installed versions (`pip freeze | grep -E 'drf-spectacular|psycopg2|redis|gspread|google-auth'`).

**DEP-02** — `.github/workflows/ci.yml` — three path errors mean `pip-audit` also runs against the wrong `requirements.txt` path and likely fails silently. The security scan is effectively bypassed until the path is fixed. Fix: correct the path to `${{ github.workspace }}/requirements.txt` (see also STR-02).

**Verdict: 7/10** — Mostly pinned; five loose `>=` pins and the broken CI audit path are the main gaps.

---

## Priority Summary

| ID | Severity | File | Line / Function | Finding | Fix |
|---|---|---|---|---|---|
| SEC-01 | 🔴 Critical | `apps/camera/views.py` | `_client_ip()` | Uses `split(',')[0]` — client-spoofable IP; camera audit logs can be forged | Change to `split(',')[-1].strip()` |
| STR-02 | 🔴 Critical | `.github/workflows/ci.yml` | lines 23, 45, Docker build | Wrong `working-directory` and `requirements.txt` paths — CI never runs | Fix paths to match actual repo structure |
| ARCH-03 | 🟠 Medium | `apps/transactions/signals.py` + `services.py` | `on_transaction_save` + `write_audit_entry` | Double `AuditLog` write on every `Transaction.save()` | Remove `_write_audit_log` from signal |
| SEC-02 | 🟠 Medium | `templates/registration/login.html` | lines 8-9 | CDN FontAwesome load with no SRI, redundant with self-hosted copy | Remove CDN `<link>` tag |
| SEC-04 | 🟠 Medium | `apps/users/views.py` | `simulate_orex_run` | TOCTOU race between SimulationRun guard and thread launch | Use `select_for_update()` + atomic guard |
| TEST-01 | 🟠 Medium | `.github/workflows/ci.yml` | test command | Per-app `tests.py` files not discovered by CI | Change test label to `armguard` |
| ARCH-01 | 🟠 Medium | `apps/users/views.py` | entire file | 1,703-line monolith; forms defined in views file | Extract to `forms.py`, split views |
| ARCH-02 | 🟠 Medium | `apps/transactions/models.py` | `Transaction.clean()` | ~400-line method | Extract to named helper functions |
| PERF-01 | 🟠 Medium | `apps/transactions/views.py` | `TransactionListView.get_queryset()` | 4 correlated subqueries per list page | Add composite indexes or denormalize |
| QUAL-01 | 🟠 Medium | `apps/users/views.py` | `SystemSettingsView.post()` | ~50 fields saved without ModelForm validation | Use `ModelForm` for `SystemSettings` |
| TEST-02 | 🟢 Low | `tests/test_transactions.py` | `TestTransactionCacheInvalidation` | Cache test doesn't exercise real save path | Rewrite as end-to-end POST test |
| TEST-03 | 🟢 Low | `tests/` | (missing) | No tests for camera upload, MFA bypass, session invalidation | Add integration tests for these paths |
| STR-01 | 🟢 Low | `apps/users/` | (missing file) | No `forms.py`; forms live in `views.py` | Create `users/forms.py` |
| DEP-01 | 🟢 Low | `requirements.txt` | 5 packages | `>=` pins on 5 packages | Pin to exact installed versions |
| SEC-03 | 🟢 Low | `settings/base.py` | `X_FRAME_OPTIONS` | Dead setting — middleware removed | Remove or add explanatory comment |
| ARCH-04 | 🟢 Low | `apps/users/views.py` | `simulate_orex_run` | `daemon=False` thread won't stop on interpreter shutdown | Set `daemon=True` |
| QUAL-02 | 🟢 Low | `apps/inventory/views.py` | `render_to_response()` | AJAX detection via `X-Requested-With` not sent by `fetch()` | Use `?format=partial` query param |
| QUAL-03 | 🟢 Low | `apps/dashboard/views.py` | `_NOMENCLATURE`, `_MODEL_ORDER` | Constants duplicated from `inventory/models.py` | Import from single source |

---

## Refactoring Opportunities

1. **`apps/users/views.py` split** — Extract to `users/forms.py` (2 form classes), `users/views/otp.py` (OTPSetupView, OTPVerifyView), `users/views/settings.py` (SystemSettingsView and helpers), `users/views/simulation.py` (OREX simulation), keeping `users/views/__init__.py` as a thin re-export. This single change reduces the file from 1,703 lines to ~300 lines per module.

2. **`Transaction.clean()` decomposition** — Extract ammo/magazine compatibility validation to `_validate_ammo_compatibility(self)`, withdrawal-specific rules to `_validate_withdrawal(self)`, and return-binding rules to `_validate_return(self)`. Keep `clean()` as an orchestrator. Each extracted function can then be unit-tested independently.

3. **Settings ModelForm** — Replace the 50-field inline POST handler in `SystemSettingsView.post()` with a Django `ModelForm` for `SystemSettings`. This adds automatic validation, CSRF, and makes adding new settings a one-line change.

4. **Camera IP helper** — Extract `_client_ip(request)` into `armguard/utils/http.py` as a shared utility to ensure all three call sites (`activity.py`, `users/models.py`, `camera/views.py`) use the same implementation and cannot diverge again.

5. **Test coverage for critical paths** — Add `tests/test_camera.py` (device lockout, HMAC key rejection, upload size limit), `tests/test_middleware.py` (MFA bypass via Token header, session invalidation on second login, CSP header presence), and rewrite `TestTransactionCacheInvalidation` as a full POST integration test.

---

*Report covers ARMGUARD_RDS_V1 as of commit `eaf5e88`. All findings are based on direct file reads of 128 Python source files, 58 HTML templates, 34 JS files, CI pipeline, and deployment scripts. No findings are inferred or invented.*
