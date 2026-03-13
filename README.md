# ARMGUARD RDS — Records and Dispensing System

A Django-based small-arms records and transaction management system for military armory operations.

---

## Requirements

- Python 3.11+
- pip

---

## Local Development Setup

### 1. Clone and enter the repo

```bash
git clone <repo-url>
cd ARMGUARD_RDS_V1
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Key variables in `.env`:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | (required) |
| `DEBUG` | Enable debug mode | `False` |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1` |
| `DJANGO_ADMIN_URL` | Admin panel URL segment | `admin` |
| `DATABASE_URL` | SQLite or Postgres URL | `sqlite:///db.sqlite3` |

### 5. Apply migrations

```bash
cd project
python manage.py migrate
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

### 7. Collect static files (production)

```bash
python manage.py collectstatic --no-input
```

### 8. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` — you will be redirected to the dashboard.

---

## Running Tests

```bash
cd project
python manage.py test armguard.tests --verbosity=2
```

The test suite covers:
- Authentication (login, logout, OTP/TOTP setup and verify, password policy)
- Permission helpers (`is_admin`, `can_add`, `can_delete`, `can_create_transaction`, etc.)
- Inventory CRUD (Pistol, Rifle, Magazine, Ammunition, Accessory — list, create, delete permissions)
- Personnel CRUD (list, detail, create/update/delete permission enforcement)
- Transactions (list, detail, create permission, cache invalidation)
- REST API endpoints (auth requirements, pagination, staff-only restrictions)
- Dashboard (stats context keys, inventory table keys, cache population and invalidation)

All 97 tests should pass with `OK`.

---

## Deployment (Docker)

```bash
docker compose up --build -d
```

See [docker-compose.yml](docker-compose.yml) for service configuration.

---

## Architecture

```
project/
  armguard/
    apps/
      api/            DRF read-only REST API (v1)
      dashboard/      Main dashboard view
      inventory/      Pistol, Rifle, Magazine, Ammo, Accessory models & views
      personnel/      Personnel records
      print/          PDF form filling (TR/PAR)
      transactions/   Withdrawal/Return transaction lifecycle
      users/          User profiles, TOTP MFA, audit log
    middleware/       Security headers, device auth, throttle
    settings/         base.py, dev.py, production.py
    static/css/       main.css (dark-theme design system)
    templates/        Base layout, 404/500 error pages
    tests/            Comprehensive test suite
    utils/            Centralised permission helpers, QR generator
```

---

## Security

- **TOTP MFA** enforced for all users (django-otp)
- **RBAC** — System Administrator / Administrator / Armorer roles
- **Rate limiting** on login (10 attempts/minute per IP)
- **CSRF** on all state-changing requests
- **Content Security Policy** headers via middleware
- **Randomised admin URL** via `DJANGO_ADMIN_URL` env var
- **WAL-mode SQLite** for concurrent read performance

---

## License

Internal use only — Air Force ARMGUARD RDS.
