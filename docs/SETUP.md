# ARMGUARD_RDS_V1 — Setup & Run Guide

**Version:** 2.1  
**Last Updated:** 2026-03-13 (Post-Session 14)  
**Platform:** Windows (PowerShell) / Linux/macOS (bash)  
**Python:** 3.12+  
**Django:** 6.0.3

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | `python --version` |
| pip | 23+ | `pip --version` |
| Git | any | for cloning |

For production servers: `nginx`, `gunicorn` (included in `requirements.txt`), `ufw`, `gnupg` (optional, for encrypted backups).

---

## 2. Quick Start (Development)

### Step 1 — Create and activate virtual environment

```powershell
# Windows
cd C:\Users\9533RDS\Desktop\hermosa\ARMGUARD_RDS_V1
python -m venv venv
venv\Scripts\activate
```

```bash
# Linux/macOS
cd /path/to/ARMGUARD_RDS_V1
python -m venv venv
source venv/bin/activate
```

### Step 2 — Install dependencies

```powershell
pip install -r requirements.txt
```

Core packages included:
- `Django==6.0.3` — framework
- `Pillow==12.1.1` — image processing (QR codes, ID cards, item tags)
- `qrcode==8.2` — QR code generation
- `PyMuPDF==1.27.1` — PDF form filling
- `whitenoise==6.12.0` — static file serving
- `python-dotenv==1.2.2` — `.env` auto-loading
- `djangorestframework==3.16.0` — REST API
- `drf-spectacular>=0.27.0` — OpenAPI 3 schema generation (`/api/v1/schema/`)
- `django-otp==1.7.0` — TOTP multi-factor authentication
- `gunicorn==22.0.0` — WSGI server for production

### Step 3 — Create `.env` from template

```powershell
copy .env.example .env
```

Edit `.env` and set at minimum `DJANGO_SECRET_KEY`. See **Section 3** for all variables.

### Step 4 — Apply migrations

```powershell
cd project
python manage.py migrate
```

### Step 5 — Create a superuser

```powershell
python manage.py createsuperuser
```

### Step 6 — Run the development server

```powershell
python manage.py runserver
```

Open: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

The root URL redirects to `/dashboard/`. Login at `/accounts/login/`.

---

## 3. Environment Variables

The application loads `.env` automatically via `python-dotenv`. Place the file one level above `project/` (i.e., at `ARMGUARD_RDS_V1/.env`).

> **Security Note:** `DJANGO_SECRET_KEY` is required in all environments — the application raises `ValueError` and refuses to start if it is missing. In production, `DJANGO_ALLOWED_HOSTS` must also be set (non-empty).

### Complete `.env` Reference

```ini
# === Core Django Settings ===
DJANGO_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(50))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# === Django Admin URL ===
# Hard-to-guess slug. Never leave as the default "admin" in production.
DJANGO_ADMIN_URL=your-secret-admin-slug

# === Unit Identification (printed on PAR/TR documents) ===
ARMGUARD_COMMANDER_NAME=RIZALDY C HERMOSO II
ARMGUARD_COMMANDER_RANK=2LT
ARMGUARD_COMMANDER_BRANCH=PAF
ARMGUARD_COMMANDER_DESIGNATION=Squadron Commander
ARMGUARD_ARMORER_NAME=
ARMGUARD_ARMORER_RANK=

# === Business Rules ===
ARMGUARD_PISTOL_MAGAZINE_MAX_QTY=4
# ARMGUARD_RIFLE_MAGAZINE_MAX_QTY=  # Leave blank for no limit

# === Production HTTPS (only set these in production) ===
# SECURE_SSL_REDIRECT=True
# SECURE_HSTS_SECONDS=31536000

# === GPG Encrypted Backups (optional) ===
# ARMGUARD_BACKUP_GPG_RECIPIENT=backup@yourdomain.com
```

### Variable Reference Table

| Variable | Required | Default | Description |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | ✅ Always | — | Django secret key; raises `ValueError` if absent |
| `DJANGO_DEBUG` | No | `True` in dev | `False` always in production |
| `DJANGO_ALLOWED_HOSTS` | ✅ Production | — | Comma-separated hostnames; raises `ValueError` if empty in prod |
| `DJANGO_ADMIN_URL` | No | `admin` | Admin URL slug; change in production |
| `ARMGUARD_COMMANDER_NAME` | No | `RIZALDY C HERMOSO II` | Printed on PAR/TR documents |
| `ARMGUARD_COMMANDER_RANK` | No | `2LT` | Commander's rank |
| `ARMGUARD_COMMANDER_BRANCH` | No | `PAF` | Branch of service |
| `ARMGUARD_COMMANDER_DESIGNATION` | No | `Squadron Commander` | Commander's designation |
| `ARMGUARD_ARMORER_NAME` | No | `''` | Armorer's name for documents |
| `ARMGUARD_ARMORER_RANK` | No | `''` | Armorer's rank |
| `ARMGUARD_PISTOL_MAGAZINE_MAX_QTY` | No | `4` | Max pistol magazines per transaction |
| `ARMGUARD_RIFLE_MAGAZINE_MAX_QTY` | No | unlimited | Max rifle magazines per transaction |
| `ARMGUARD_BACKUP_GPG_RECIPIENT` | No | — | GPG recipient email for encrypted backups |

---

## 4. Settings Module

The project uses a split-settings pattern. Select the correct module with `DJANGO_SETTINGS_MODULE`:

| Mode | Settings Module | Use When |
|---|---|---|
| Development | `armguard.settings.development` | Local dev, testing |
| Production | `armguard.settings.production` | Any server deployment |

`manage.py` defaults to `armguard.settings.development`.
`wsgi.py` and `asgi.py` default to `armguard.settings.production`.

To override on the command line:

```powershell
# Windows
set DJANGO_SETTINGS_MODULE=armguard.settings.production
python manage.py check --deploy
```

```bash
# Linux/macOS
DJANGO_SETTINGS_MODULE=armguard.settings.production python manage.py check --deploy
```

---

## 5. Database Setup

### Migration History

`python manage.py migrate` applies all migrations in order:

| App | Migrations |
|---|---|
| `armguard.apps.inventory` | `0001_initial` |
| `armguard.apps.personnel` | `0001_initial` |
| `armguard.apps.transactions` | `0001_initial`, `0002_add_ammo_return_indexes`, `0003_sanitize_par_upload` |
| `armguard.apps.users` | `0001_initial`, `0002_auditlog_and_session_key`, `0003_auditlog_useragent_hash_deletedrecord` |
| `otp_totp` | 3 migrations (TOTP device tables) |
| `otp_static` | 3 migrations (static OTP backup code tables) |
| `rest_framework.authtoken` | 1 migration (API token table) |
| `django.contrib.*` | (built-in) |

### Switch to PostgreSQL (Production)

1. Install the driver:
   ```bash
   pip install psycopg2-binary
   ```
2. Update `settings/base.py` `DATABASES` section to use the `postgresql` engine.
3. Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` in `.env`.
4. Run `python manage.py migrate`.

---

## 6. Multi-Factor Authentication (TOTP)

ARMGUARD enforces TOTP two-factor authentication for **all authenticated sessions**. On first login, the user is redirected automatically through the OTP enrollment flow:

1. `/accounts/otp/setup/` — displays a QR code for the user's TOTP device
2. User scans the QR code with any TOTP app (Google Authenticator, Authy, etc.)
3. User enters the 6-digit code to confirm enrollment
4. All subsequent logins require a valid OTP token at `/accounts/otp/verify/`

> **Bypass via admin:** Admin users can manage OTP devices under Django Admin → OTP TOTP → TOTP Devices.

> **Backup codes:** `otp_static` devices provision 10 one-time recovery codes per user.

`OTPRequiredMiddleware` blocks all protected URLs for any session that has not completed OTP verification and redirects to the appropriate step.

---

## 7. Running Tests

```powershell
cd project
python manage.py test armguard.tests
```

**Expected result:** `Ran 113 tests in ~10s ... OK`

Run with coverage:
```powershell
coverage run manage.py test armguard.tests && coverage report
```
(Requires `pip install coverage`; coverage config in `project/.coveragerc`.)

The test suite covers:
- PDF extension + magic-bytes validation
- Role-based access control (withdraw/return permission checks)
- Withdrawal/return workflow integration (all item types)
- Issuance-type propagation
- TransactionLogs status machine (Open → Partially Returned → Closed)
- API rate-limiting throttle (decorator + DRF)
- Atomic quantity adjustment (F() + Greatest)
- Service layer functions (6 functions isolated)
- Personnel model methods (`has_pistol_issued`, `can_return_*`, `set_issued`)
- Audit signal emission (write to `armguard.audit` logger)
- Security headers (CSP, Referrer-Policy, frame-ancestors)
- Transaction cascade, concurrency, and duplicate-validation safety (16 tests)

---

## 7b. CI/CD — GitHub Actions

A CI pipeline runs automatically on push/PR to `main` or `develop`:

```
.github/workflows/ci.yml
```

Steps: lint (flake8), test (pytest/manage.py), coverage report, pip-audit security scan, Docker build verification.

---

## 8. Management Commands

### 8.1 Database Backup

Creates a hot-copy of the SQLite database with a SHA-256 checksum sidecar file:

```bash
python manage.py db_backup
python manage.py db_backup --output /path/to/backups --keep 7
```

| Flag | Default | Description |
|---|---|---|
| `--output PATH` | `<project>/backups/` | Destination directory |
| `--keep N` | `5` | Number of backup sets to retain |

Produces:
- `armguard_<timestamp>.sqlite3` — hot-copy backup
- `armguard_<timestamp>.sqlite3.sha256` — SHA-256 checksum for integrity verification

### 8.2 Export Audit Log

Export the `AuditLog` DB table to CSV:

```bash
python manage.py export_audit_log
python manage.py export_audit_log --days 30 --action LOGIN --user admin --output /tmp/audit.csv
```

| Flag | Default | Description |
|---|---|---|
| `--days N` | all records | Limit to last N days |
| `--action TYPE` | all | Filter by action (LOGIN/LOGOUT/CREATE/UPDATE/DELETE) |
| `--user USERNAME` | all | Filter by username |
| `--output PATH` | stdout | Write CSV to file path |

### 8.3 Cleanup Sessions

Remove expired Django sessions from the database:

```bash
python manage.py cleanup_sessions           # dry-run (shows count only)
python manage.py cleanup_sessions --delete  # actually deletes
```

---

## 9. Static Files

WhiteNoise serves static files as part of the Django WSGI application. No separate Nginx `alias` is required for `/static/`.

For production, run once before starting the server:

```bash
python manage.py collectstatic --noinput
```

---

## 10. Production Deployment

### 10.1 Automated Deploy Script (Linux/Ubuntu)

`scripts/deploy.sh` automates the full production setup on a fresh server:

```bash
chmod +x scripts/deploy.sh
sudo bash scripts/deploy.sh
```

The script:
1. Installs system packages (Python 3.12, nginx, ufw, gnupg)
2. Creates a dedicated `armguard` system user
3. Clones the repo and creates the virtual environment
4. Generates a production `.env` file with a random `SECRET_KEY`
5. Runs `migrate` and `collectstatic`
6. Installs and enables the `armguard-gunicorn.service` systemd unit
7. Configures nginx (login rate-limit 5 req/min, blocks script execution in `/media/`)
8. Sets up ufw firewall (ports 80, 443)
9. Registers a daily cron job for database backups

### 10.2 Manual Gunicorn Start

```bash
DJANGO_SETTINGS_MODULE=armguard.settings.production \
gunicorn armguard.wsgi:application \
  --workers 3 \
  --bind 127.0.0.1:8000 \
  --timeout 120
```

### 10.3 Systemd Service

```bash
sudo cp scripts/armguard-gunicorn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable armguard-gunicorn
sudo systemctl start armguard-gunicorn
```

The service unit is hardened: `PrivateTmp=true`, `NoNewPrivileges=true`, `ProtectSystem=strict`.

### 10.4 Nginx Configuration

```bash
sudo cp scripts/nginx-armguard.conf /etc/nginx/sites-available/armguard
sudo ln -s /etc/nginx/sites-available/armguard /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 10.5 Encrypted Backup Cron

When `ARMGUARD_BACKUP_GPG_RECIPIENT` is set, `scripts/db-backup-cron.sh`:
1. Runs `db_backup` management command
2. GPG-encrypts the `.sqlite3` backup to `.sqlite3.gpg`
3. Shreds the plaintext copy
4. Retains the last 7 encrypted backups

```bash
export ARMGUARD_BACKUP_GPG_RECIPIENT=backup@yourdomain.com
bash scripts/db-backup-cron.sh
```

---

## 11. Docker Deployment (Development)

A multi-stage `Dockerfile` and `docker-compose.yml` are included:

```bash
docker-compose up --build
```

The compose configuration mounts source code for live reload and persists SQLite and media files via named volumes. Uses `armguard.settings.development` by default.

---

## 12. URL Reference

| URL | View | Auth Required |
|---|---|---|
| `/` | Redirect → `/dashboard/` | ✅ |
| `/dashboard/` | `dashboard_view` | ✅ |
| `/accounts/login/` | `_RateLimitedLoginView` (10 POST/min) | ❌ |
| `/accounts/logout/` | `logout_view` (POST-only) | ✅ |
| `/accounts/otp/setup/` | `OTPSetupView` | ✅ (unverified) |
| `/accounts/otp/verify/` | `OTPVerifyView` | ✅ (unverified) |
| `/personnel/` | Personnel list | ✅ |
| `/inventory/pistols/` | Pistol list | ✅ |
| `/inventory/rifles/` | Rifle list | ✅ |
| `/transactions/` | Transaction list | ✅ |
| `/transactions/create/` | New transaction | ✅ + `can_process_withdrawal` |
| `/users/` | User list | ✅ + System Administrator |
| `/api/v1/` | REST API root | ✅ (token or session) |
| `/api/v1/auth/token/` | Obtain API token | ✅ credentials |
| `/<DJANGO_ADMIN_URL>/` | Django admin | ✅ staff |
| `/robots.txt` | Robots exclusion | ❌ |
| `/.well-known/security.txt` | Security contact | ❌ |

---

## 13. Default User Roles

| Role | Personnel | Inventory (Add) | Inventory (Edit/Delete) | Transactions | Print | User Mgmt |
|---|---|---|---|---|---|---|
| System Administrator | ✅ Full | ✅ | ✅ | ✅ | ✅ | ✅ |
| Administrator | ✅ Full | ✅ | ✅ | ✅ | ✅ | ❌ |
| Armorer | ❌ | ✅ Add only | ❌ | ✅ | ✅ | ❌ |

---

## 14. Common Issues & Solutions

| Problem | Cause | Solution |
|---|---|---|
| `ValueError: DJANGO_SECRET_KEY is not set` | Missing env var | Add `DJANGO_SECRET_KEY` to `.env` |
| `ValueError: ALLOWED_HOSTS must not be empty` | Production with no hosts | Set `DJANGO_ALLOWED_HOSTS` in `.env` |
| `ModuleNotFoundError: No module named 'armguard.apps.X'` | Wrong working directory | Run `manage.py` from `project/` |
| `No such table: inventory_pistol` | Migrations not applied | `python manage.py migrate` |
| Login redirects to `/accounts/login/?next=/dashboard/` | Not authenticated | Create superuser and log in |
| Redirected to `/accounts/otp/setup/` after login | OTP not enrolled | Scan the QR code and confirm 6-digit token |
| Redirected to `/accounts/otp/verify/` every page | OTP not verified this session | Enter the current TOTP code |
| `Static files not loading` | `DEBUG=False` without collectstatic | Run `python manage.py collectstatic` |

---

## 15. Media Files

User-uploaded media is stored in `project/media/`:

```
project/media/
├── personnel_images/
├── personnel_id_cards/
├── qr_code_images_personnel/
├── qr_code_images_pistol/
├── qr_code_images_rifle/
├── serial_images_pistol/
├── serial_images_rifle/
├── item_id_tags/
└── TR_PDF_TEMPLATE/
```

Development: served automatically by Django when `DEBUG=True`.  
Production: serve `MEDIA_ROOT` via nginx. The nginx config in `scripts/nginx-armguard.conf` includes a `location /media/` block that blocks server-side script execution.

---

*ARMGUARD RDS V1 Setup Guide — v2.0 (Post-Session 10)*
