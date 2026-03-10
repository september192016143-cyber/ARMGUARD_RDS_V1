# ARMGUARD_RDS_V1 — Architecture Overview

**Version:** 2.0  
**Last Updated:** 2026-03-09 (Post-Session 10)  
**Project Path:** `ARMGUARD_RDS_V1/project/`

---

## 1. High-Level Architecture

ARMGUARD_RDS_V1 is a Django-based armory management system following a **namespaced multi-app architecture** within a single Django project.

```
ARMGUARD_RDS_V1/
├── docs/                          ← Documentation (this folder)
├── project/                       ← Django project root
│   ├── manage.py
│   ├── db.sqlite3                 ← SQLite database (dev)
│   └── armguard/                  ← Main package
│       ├── settings/              ← Split settings package
│       │   ├── base.py            ← Shared config (loaded by all envs)
│       │   ├── development.py     ← DEBUG=True, localhost ALLOWED_HOSTS
│       │   └── production.py      ← DEBUG=False, HTTPS/HSTS, secure cookies
│       ├── middleware/            ← Custom middleware
│       │   ├── security.py        ← CSP + Referrer-Policy + Permissions-Policy
│       │   ├── session.py         ← SingleSessionMiddleware
│       │   └── mfa.py             ← OTPRequiredMiddleware (TOTP enforcement)
│       ├── urls.py                ← Root URL dispatcher
│       ├── wsgi.py
│       ├── asgi.py
│       ├── static/
│       │   └── css/
│       │       └── main.css       ← Custom CSS (225 lines, no Bootstrap)
│       ├── templates/             ← Shared template directory
│       │   ├── base.html          ← Master layout + 30s inventory polling JS
│       │   ├── robots.txt         ← Disallows /admin/ and sensitive paths
│       │   ├── security.txt       ← Responsible disclosure contact
│       │   ├── dashboard/
│       │   ├── inventory/
│       │   ├── personnel/
│       │   ├── transactions/
│       │   ├── users/
│       │   ├── print_handler/
│       │   └── registration/
│       │       ├── login.html
│       │       ├── otp_setup.html ← TOTP QR enrollment
│       │       └── otp_verify.html← TOTP token challenge
│       └── apps/                  ← All feature apps (namespaced)
│           ├── core/              ← Config stub (no views/models)
│           ├── dashboard/         ← Dashboard app (live stats)
│           ├── inventory/         ← Weapons, ammo, accessories
│           ├── personnel/         ← Personnel records
│           ├── transactions/      ← Withdrawal/return workflow
│           │   └── services.py    ← Service layer (6 extracted functions)
│           ├── users/             ← User profiles, AuditLog, DeletedRecord, PasswordHistory
│           │   ├── validators.py            ← PasswordHistoryValidator
│           │   └── management/
│           │       └── commands/
│           │           ├── db_backup.py         ← SQLite hot-copy + SHA-256 + secure delete
│           │           ├── export_audit_log.py  ← CSV audit export
│           │           └── cleanup_sessions.py  ← Session cleanup
│           ├── print/             ← PDF, QR, ID card printing
│           ├── api/               ← Read-only REST API (DRF)
│           └── utils/             ← QR & tag generation utilities
├── scripts/                       ← Production deployment scripts
│   ├── deploy.sh                  ← Full automated server setup
│   ├── update-server.sh           ← Pull & restart (rolling update)
│   ├── armguard-gunicorn.service  ← Hardened systemd service unit
│   ├── nginx-armguard.conf        ← Nginx config (rate limit + media block)
│   ├── setup-firewall.sh          ← ufw firewall rules
│   └── db-backup-cron.sh          ← GPG-encrypted nightly backup cron
├── Dockerfile                     ← Multi-stage build (Python 3.12-slim)
├── docker-compose.yml             ← Dev compose (SQLite + media volumes)
├── .dockerignore
├── .env.example                   ← All variables documented with defaults
├── requirements.txt
└── venv/
```

---

## 2. App Inventory

### 2.1 `armguard.apps.core`
- **Role:** Configuration only — no models, no views
- **Files:** `__init__.py`, `apps.py`
- **Key:** Settings and URL configuration live outside this app at `armguard/settings.py` and `armguard/urls.py`

### 2.2 `armguard.apps.dashboard`
- **Role:** Real-time dashboard with live DB statistics
- **Views:** `dashboard_view` (FBV, `@login_required`, 60-second cache)
- **Key Features:**
  - `_build_inventory_table()` — per-model firearm breakdown (total/available/issued/assigned)
  - `_build_ammo_table()` — per-type ammunition breakdown
  - Nomenclature mapping dict (`_NOMENCLATURE`) for military-standard item names
  - Stat cards: Total Personnel, Total Pistols, Total Rifles, Active Transactions

### 2.3 `armguard.apps.inventory`
- **Role:** All physical item records
- **Models:** `Pistol`, `Rifle`, `Magazine`, `Ammunition`, `Accessory`, `Category`
- **Analytics Models:** `Inventory_Analytics`, `AnalyticsSnapshot` (in `inventory_analytics_model.py`)
- **Abstract Base:** `SmallArm` (in `base_models.py`) — shared fields/methods for Pistol and Rifle
- **Key Features:**
  - Custom primary keys: `IP-<model_code>-<serial>` for pistols, `IR-<model_code>-<serial>` for rifles
  - Atomic `adjust_quantity()` using `F() + Greatest(0, ...)` — safe for concurrent updates
  - `can_be_withdrawn()` / `can_be_returned()` — business rule enforcement on model
  - QR code + item tag generation on first save

### 2.4 `armguard.apps.personnel`
- **Role:** Military/Air Guard member records
- **Model:** `Personnel` with `Personnel_ID` as custom primary key
- **Key Features:**
  - Auto-generated Personnel_ID format: `PEP-<AFSN>-<timestamp>` (enlisted) / `POF_O-<AFSN>-<timestamp>` (officer)
  - Personal QR code generated on first save
  - **Computed properties** derive live issuance state from TransactionLogs (single source of truth):
    - `get_current_pistol()`, `get_current_rifle()`, `get_current_pistol_magazine()`, etc.
  - Tracks item issuance via denormalized CharFields (legacy, mitigated by computed properties)
  - `Personnel_ID` preview JS in forms

### 2.5 `armguard.apps.transactions`
- **Role:** All withdrawal and return operations
- **Models:** `Transaction`, `TransactionLogs`
- **Service Layer:** `services.py` — 6 extracted functions (`propagate_issuance_type`, `sync_personnel_and_items`, `adjust_consumable_quantities`, `create_withdrawal_log`, `update_return_logs`, `write_audit_entry`)
- **Signals:** Post-save audit logging + `TransactionLogs.issuance_type` resync
- **Key Features:**
  - `Transaction.save()` is a thin ~45-line orchestrator calling the service layer
  - `Transaction.clean()` enforces all business rules (item availability, personnel eligibility, quantity caps)
  - `_validate_pdf_extension()` + magic-bytes check on PAR document uploads
  - `_sanitize_par_upload()` — NFKD-normalizes and strips unsafe characters from uploaded PAR filenames
  - Custom permissions: `can_process_withdrawal`, `can_process_return`, `can_view_transaction_logs`
  - Composite DB indexes for fast analytics queries

### 2.6 `armguard.apps.users`
- **Role:** System user management with armory-specific roles, audit trail, and deleted-record archive
- **Models:**
  - `UserProfile` (OneToOne to AUTH_USER_MODEL) — `role` field + `last_session_key` (single-session enforcement)
  - `AuditLog` — queryable DB record for every LOGIN/LOGOUT/CREATE/UPDATE/DELETE; includes `user_agent`, `integrity_hash` (SHA-256)
  - `DeletedRecord` — JSON snapshot of any hard-deleted record with `deleted_by` FK and `deleted_at` timestamp
- **Roles:** `System Administrator`, `Administrator`, `Armorer`
- **Auto-creation:** `post_save` signal on User creates a `UserProfile` automatically
- **Signals:** `user_logged_in` / `user_logged_out` write `AuditLog` rows and update `last_session_key`
- **Management Commands:**
  - `db_backup` — hot SQLite copy + SHA-256 sidecar with `--keep N` rotation
  - `export_audit_log` — CSV export with `--days`, `--action`, `--user`, `--output` filters
  - `cleanup_sessions` — dry-run + `--delete` expired session cleanup
- **Views:** `UserListView`, `UserCreateView`, `UserEditView`, `logout_view`, `OTPSetupView`, `OTPVerifyView`

### 2.7 `armguard.apps.api`
- **Role:** Read-only REST API for integration and reporting
- **Framework:** Django REST Framework 3.16.0
- **Authentication:** Session auth + Token auth (`POST /api/v1/auth/token/`)
- **Endpoints:** Read-only `ModelViewSet`s for `Pistol`, `Rifle`, `Personnel`, `Transaction`
- **Rate Limiting:** `AnonRateThrottle` 10/min; `UserRateThrottle` 30/min
- **Pagination:** 50 items per page
- **Bonus endpoint:** `GET /api/v1/last-modified/` — staleness detection for the 30-second frontend polling script

### 2.8 `armguard.apps.print`
- **Role:** Print management for QR codes, item tags, personnel ID cards, transaction receipts
- **Key Files:**
  - `print_config.py` — layout constants (QR size, card dimensions, font sizes)
  - `pdf_filler/form_filler.py` — transaction receipt/form PDF filling
  - `pdf_filler/form_config.py` — PDF field coordinate mapping
- **URL namespace:** `print_handler` (backward-compatible with RDS)

### 2.9 `armguard.apps.utils`
- **Role:** Shared utilities for media generation
- **Files:**
  - `qr_generator.py` — QR code PNG generation
  - `item_tag_generator.py` — Item ID tag image generation
  - `personnel_id_card_generator.py` — Personnel ID card image generation
- **Access pattern:** Also copied to `project/utils/` so `from utils.X import` works at project root PYTHONPATH

---

## 3. Data Flow

### 3.1 Transaction Workflow

```
User (Form Submit)
  │
  ▼
WithdrawalReturnTransactionForm.is_valid()
  │  → Field-level validation
  │
  ▼
Transaction.save(user=request.user)
  │
  ├─ self.clean()               ← Business rules (withdrawal/return eligibility)
  │
  ├─ db_transaction.atomic():
  │   ├─ Adjust item status     (Available → Issued / Issued → Available)
  │   ├─ Adjust quantity pools  (Magazine, Ammunition, Accessory)
  │   ├─ sync Personnel fields  (set_issued / clear_issued)
  │   ├─ Create/Update TransactionLogs
  │   └─ super().save()
  │
  └─ signals.py (post_save):
      ├─ Audit log entry
      └─ Resync TransactionLogs.issuance_type (REC-06)
```

### 3.2 Authentication Flow (with MFA)

```
User visits any URL
  │
  ▼
LoginRequiredMixin / @login_required
  │  → Redirect to /accounts/login/ if not authenticated
  │
  ▼
_RateLimitedLoginView (10 POST/min per IP)
  │  → Template: registration/login.html
  │  → Validates username/password
  │  → Writes AuditLog(action='LOGIN') + updates last_session_key
  │
  ▼
OTPRequiredMiddleware
  │  → If user has no OTP device: redirect to /accounts/otp/setup/
  │  → If OTP device exists but not verified this session: redirect to /accounts/otp/verify/
  │  → On valid token: django_otp.login() marks session as verified
  │
  ▼
SingleSessionMiddleware
  │  → Compares session.session_key to UserProfile.last_session_key
  │  → Mismatch: force-logout (stale session from another device)
  │
  ▼
Dashboard / protected view
```

Role check in view (`_can_manage_*`, `_can_create_transaction`, etc.) returns 403 if role is insufficient.

### 3.3 Dashboard Data Flow

```
GET /dashboard/
  │
  ▼
cache.get('dashboard_stats', 60s)
  │
  ├─ Cache HIT → return cached context dict
  │
  └─ Cache MISS:
      ├─ _build_inventory_table()   ← Pistol/Rifle aggregates per model
      ├─ _build_ammo_table()        ← Ammunition aggregates per type
      ├─ Personnel.objects.count()
      ├─ Transaction.objects.filter(active=True).count()
      └─ cache.set(context, 60s)
```

---

## 4. Design Patterns

| Pattern | Where Used | Benefit |
|---|---|---|
| Abstract base model | `SmallArm` → Pistol/Rifle | Eliminates ~95% code duplication |
| Computed properties | `Personnel.get_current_pistol()` etc. | Single source of truth via TransactionLogs |
| Atomic transactions | `Transaction.save()` | All-or-nothing write semantics |
| Atomic F() updates | `adjust_quantity()` | Eliminates read-modify-write race condition |
| Signal-based logging | `transactions/signals.py` | Decoupled audit trail |
| CBV + UserPassesTestMixin | Inventory, Personnel, User views | Clean RBAC separation |
| FBV for custom logic | `create_transaction`, `dashboard_view` | Flexibility where CBV adds no value |
| 60-second cache | Dashboard | Prevents expensive DB aggregates on every page load |
| POST-only logout | `@require_POST logout_view` | CSRF-safe session termination |
| ENV-based secrets | `settings.py` | No hardcoded credentials in source control |

---

## 5. Key Design Decisions

### 5.1 `armguard.apps.X` Namespace
All feature apps live under `armguard/apps/` and are registered as `armguard.apps.X`. This:
- Makes the package relationship explicit
- Prevents import namespace collisions
- Forces all cross-app imports to be fully qualified: `from armguard.apps.inventory.models import Pistol`

### 5.2 Dedicated `dashboard` App
In RDS, dashboard logic was inside `core/views.py`. V1 moves this to a dedicated `dashboard` app:
- `core` is purely infrastructure (settings, urls, wsgi, asgi)
- `dashboard` owns its templates, views, and context building
- Easier to test, extend, or replace in isolation

### 5.3 No External UI Framework
All CSS is hand-written in `armguard/static/css/main.css` (225 lines). No Bootstrap, Tailwind, or other framework. This:
- Avoids CDN dependencies
- Gives full control over the design system
- Results in a smaller, faster CSS payload

### 5.4 SQLite for Development, PostgreSQL for Production
The `settings/development.py` uses SQLite. All models are designed to be PostgreSQL-compatible (no SQLite-only features). In `settings/base.py`, update `DATABASES` and add `psycopg2` for a production PostgreSQL deployment.

---

## 6. Security Architecture

| Layer | Control | Implementation |
|---|---|---|
| Authentication | Django's built-in auth | `LoginRequiredMixin` / `@login_required` everywhere |
| Multi-Factor Auth | TOTP (django-otp) | `OTPRequiredMiddleware` enforces 2FA on all protected views |
| Single-Session | One active session per user | `SingleSessionMiddleware` + `UserProfile.last_session_key` |
| Authorization | Role-based | `UserProfile.role` checked in every sensitive view |
| CSRF | Django middleware | `CsrfViewMiddleware` in `MIDDLEWARE` |
| Clickjacking | X-Frame-Options DENY | `XFrameOptionsMiddleware` + CSP `frame-ancestors 'none'` |
| Security Headers | Custom middleware | `SecurityHeadersMiddleware` sets CSP, Referrer-Policy, Permissions-Policy |
| Session management | POST-only logout + timeout | `@require_POST`; `SESSION_COOKIE_AGE=28800` (8 h) |
| Password security | Django validators | 5 validators: min length **12**, similarity, common, numeric, **PasswordHistoryValidator** (last 5) |
| Password history | `PasswordHistoryValidator` | Prevents reuse of last 5 passwords; `PasswordHistory` model stores hashed history |
| Secret management | Environment vars only | `base.py` raises `ValueError` if `DJANGO_SECRET_KEY` is absent |
| Admin URL | Configurable slug | `ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL')` — never exposed at `/admin/` in production |
| Login brute-force | Rate limit | `_RateLimitedLoginView` — 10 POST/min per IP via `@ratelimit` |
| API rate limiting | DRF throttle | `AnonRateThrottle` 10/min; `UserRateThrottle` 30/min |
| DB-level constraints | `CheckConstraint` | 9 constraints across 5 models (item status, quantity ≥ 0, personnel status) |
| Audit trail (file) | Signal-based logging | `armguard.audit` `RotatingFileHandler` on all model mutations |
| Audit trail (DB) | `AuditLog` model | Queryable DB records for every LOGIN/LOGOUT/CREATE/UPDATE/DELETE |
| Audit integrity | SHA-256 hash | Each `AuditLog` row has an `integrity_hash` computed on write |
| Deletion archive | `DeletedRecord` | JSON snapshot written before any hard-delete |
| Backup security | Secure delete | Old backup files overwritten with zeros before `unlink()` via `_secure_delete()` |
| FK integrity | `on_delete` rules | PROTECT for critical records, SET_NULL for referential safety |
| Robots/security.txt | Crawler control | `/robots.txt` disallows sensitive paths; `/.well-known/security.txt` present |
| Production HTTPS | `settings/production.py` | `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS=31536000`, secure cookies |
