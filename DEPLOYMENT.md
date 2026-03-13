# ArmGuard RDS V1 — Deployment Reference

> **Quick start:** see [`scripts/DEPLOY_GUIDE.md`](scripts/DEPLOY_GUIDE.md) for the full step-by-step playbook.  
> This document is a top-level summary linking every deployment artifact.

---

## Prerequisites

| Requirement | Version / Notes |
|---|---|
| OS | Ubuntu Server 24.04 LTS (bare metal or VPS) |
| Python | 3.12 |
| Nginx | 1.24+ |
| Gunicorn | 23+ (installed from `requirements.txt`) |
| Git | any recent version |
| SQLite | 3.45+ (ships with Python 3.12) |

---

## One-Command Deploy

```bash
sudo git clone https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git /var/www/ARMGUARD_RDS_V1
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/deploy.sh --domain YOUR_SERVER_IP --lan-ip YOUR_SERVER_IP
```

`deploy.sh` automates every step: venv creation, pip install, `.env` generation, `migrate`, `collectstatic`, systemd service registration, Nginx config, UFW firewall, Fail2Ban, log rotation, and backup cron.

---

## Deployment Artifacts

| File | Purpose |
|---|---|
| [`scripts/deploy.sh`](scripts/deploy.sh) | One-shot deploy — idempotent, safe to re-run on updates |
| [`scripts/update-server.sh`](scripts/update-server.sh) | Pull latest code + restart services |
| [`scripts/gunicorn.conf.py`](scripts/gunicorn.conf.py) | Gunicorn worker/thread/timeout config |
| [`scripts/gunicorn-autoconf.sh`](scripts/gunicorn-autoconf.sh) | Auto-tunes worker count to CPU/RAM |
| [`scripts/armguard-gunicorn.service`](scripts/armguard-gunicorn.service) | systemd service unit |
| [`scripts/nginx-armguard.conf`](scripts/nginx-armguard.conf) | Nginx config (HTTP or HTTPS with public cert) |
| [`scripts/nginx-armguard-ssl-lan.conf`](scripts/nginx-armguard-ssl-lan.conf) | Nginx config (HTTPS with self-signed cert for LAN) |
| [`scripts/setup-firewall.sh`](scripts/setup-firewall.sh) | UFW + Fail2Ban + unattended-upgrades setup |
| [`scripts/backup.sh`](scripts/backup.sh) | Backup: SQLite + media + .env, 7-day retention |
| [`scripts/db-backup-cron.sh`](scripts/db-backup-cron.sh) | Lightweight cron-only DB backup |
| [`scripts/renew-ssl-cert.sh`](scripts/renew-ssl-cert.sh) | SSL certificate renewal helper |
| [`Dockerfile`](Dockerfile) | Multi-stage Docker image (builder + runtime) |
| [`docker-compose.yml`](docker-compose.yml) | Docker Compose for local development |
| [`scripts/SSL_SELFSIGNED.md`](scripts/SSL_SELFSIGNED.md) | Self-signed SSL guide for LAN deployments |

---

## Key Paths (on-server)

| Path | Description |
|---|---|
| `/var/www/ARMGUARD_RDS_V1/` | Application root |
| `/var/www/ARMGUARD_RDS_V1/project/` | Django project root (manage.py here) |
| `/var/www/ARMGUARD_RDS_V1/.env` | Environment secrets (SECRET_KEY, ALLOWED_HOSTS, etc.) |
| `/var/www/ARMGUARD_RDS_V1/venv/` | Python virtual environment |
| `/var/log/armguard/` | Gunicorn access + error logs, backup log |
| `/var/backups/armguard/` | Local backup snapshots (7-day rolling) |
| `/mnt/backup/armguard/` | External drive backup mirror (when mounted) |
| `/etc/gunicorn/workers.env` | Auto-tuned worker count (written by gunicorn-autoconf.sh) |

---

## Environment Variables (`.env`)

```env
# Django core
DJANGO_SECRET_KEY=<64-char random string>
DJANGO_SETTINGS_MODULE=armguard.settings.production
DJANGO_ALLOWED_HOSTS=192.168.0.11   # or your domain
DJANGO_ADMIN_URL=admin-<random>/    # obfuscate the admin URL

# HTTPS (set to True after SSL is configured)
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
CSRF_TRUSTED_ORIGINS=http://192.168.0.11

# Database (defaults to SQLite; omit for SQLite)
# DATABASE_URL=postgres://user:pass@host:5432/dbname

# Backup
ARMGUARD_BACKUP_GPG_RECIPIENT=       # leave blank to skip GPG encryption
```

---

## Backup Strategy

`scripts/backup.sh` — runs every 3 hours via cron, backs up:
1. SQLite database (hot dump via Django management command)
2. `media/` directory (personnel ID card images, etc.)
3. `.env` file (optionally GPG-encrypted)

**Install cron entry (once):**

```bash
(crontab -l 2>/dev/null | grep -v 'backup.sh'; \
 echo '0 */3 * * * nice -n 19 ionice -c 3 /var/www/ARMGUARD_RDS_V1/scripts/backup.sh >> /var/log/armguard/backup.log 2>&1') \
| crontab -
```

**Verify backups are running:**

```bash
tail -f /var/log/armguard/backup.log
ls /var/backups/armguard/
```

**Restore a backup:**

```bash
# List available snapshots
ls /var/backups/armguard/

# Restore DB from a snapshot (replace TIMESTAMP)
sudo systemctl stop armguard-gunicorn
cp /var/backups/armguard/TIMESTAMP/db.sqlite3 /var/www/ARMGUARD_RDS_V1/project/db.sqlite3
sudo systemctl start armguard-gunicorn
```

---

## Log Rotation

`deploy.sh` installs a logrotate config at `/etc/logrotate.d/armguard` that:
- Rotates `/var/log/armguard/*.log` daily
- Keeps 30 days of compressed history
- Sends `SIGUSR1` to Gunicorn after rotation so it reopens log file handles

**Manual logrotate config** (if not using `deploy.sh`):

```
/var/log/armguard/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        systemctl kill -s USR1 armguard-gunicorn 2>/dev/null || true
    endscript
}
```

Save to `/etc/logrotate.d/armguard` and test with:

```bash
sudo logrotate --debug /etc/logrotate.d/armguard
```

---

## PostgreSQL Migration (Recommended for Production)

SQLite works for single-server, low-concurrency deployments. For multi-user production use, migrate to PostgreSQL:

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y
sudo -u postgres createuser armguard
sudo -u postgres createdb armguard_db -O armguard
sudo -u postgres psql -c "ALTER USER armguard PASSWORD 'STRONG_PASSWORD';"

# Export data from SQLite
cd /var/www/ARMGUARD_RDS_V1/project
source ../venv/bin/activate
python manage.py dumpdata --natural-foreign --natural-primary \
  --exclude=contenttypes --exclude=auth.permission \
  -o /tmp/armguard_data.json

# Update .env
echo "DATABASE_URL=postgres://armguard:STRONG_PASSWORD@localhost:5432/armguard_db" \
  >> /var/www/ARMGUARD_RDS_V1/.env

# Add psycopg2 to requirements
echo "psycopg2-binary>=2.9" >> /var/www/ARMGUARD_RDS_V1/requirements.txt
pip install psycopg2-binary

# Apply schema and load data
python manage.py migrate
python manage.py loaddata /tmp/armguard_data.json

sudo systemctl restart armguard-gunicorn
```

---

## Docker (Development / Testing)

```bash
# Development with hot-reload
docker compose up --build

# Production image build test
docker build -t armguard-rds .
docker run --env-file .env -p 8000:8000 armguard-rds
```

See [`docker-compose.yml`](docker-compose.yml) and [`Dockerfile`](Dockerfile) for full details.

---

## Running Tests

```bash
cd project/
python manage.py test armguard.tests --verbosity=2

# With coverage report
coverage run manage.py test armguard.tests
coverage report
coverage html   # generates htmlcov/index.html
```

See [`project/.coveragerc`](project/.coveragerc) for coverage configuration (70% minimum threshold).

---

## CI/CD

GitHub Actions pipeline at [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to `main`/`develop`:
- Lint (`flake8`)
- Tests with coverage
- Security audit (`pip-audit`)
- Docker build smoke test

---

## Common Maintenance Commands

```bash
# Restart application
sudo systemctl restart armguard-gunicorn

# View live logs
sudo tail -f /var/log/armguard/gunicorn.log

# Pull updates and restart
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/update-server.sh

# Run Django migrations after update
cd /var/www/ARMGUARD_RDS_V1/project
sudo -u armguard ../venv/bin/python manage.py migrate

# Collect static files after update
sudo -u armguard ../venv/bin/python manage.py collectstatic --noinput

# Check for security regressions
sudo -u armguard ../venv/bin/python manage.py check --deploy
```
