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
| Gunicorn | 22+ (installed from `requirements.txt`) |
| Git | any recent version |
| SQLite | 3.45+ (ships with Python 3.12) |
| Avahi | `avahi-daemon libnss-mdns` — installed by `deploy.sh`; enables `armguard.local` mDNS hostname on the LAN |

---

## One-Command Deploy

```bash
sudo git clone https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git /var/www/ARMGUARD_RDS_V1
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/deploy.sh --domain armguard.local --lan-ip YOUR_LAN_IP
```

> Tip: pass `--static-ip 192.168.0.11 --gateway 192.168.0.1` to configure a static LAN IP via netplan before deploying.

`deploy.sh` automates every step:
- System packages (Python, Nginx, Avahi, image libs, MuPDF tools)
- Avahi mDNS — sets hostname to `armguard`, enables `armguard.local` on the LAN
- Self-signed SSL certificate generation (with SAN for both LAN IP and `armguard.local`)
- System user `armguard` creation
- Virtual environment + pip install
- `.env` file generation (with `armguard.local` in `ALLOWED_HOSTS`)
- Font Awesome 6.5.0 local download (SHA256-verified; no CDN dependency)
- `migrate`, `setup_groups`, `backfill_user_groups`, `collectstatic`
- Systemd service registration (`armguard-gunicorn`)
- Nginx config + proxy-params snippet
- UFW firewall + Fail2Ban + unattended-upgrades
- Log rotation
- Daily DB backup cron (02:00 AM via `db-backup-cron.sh`)
- Every-3-hour full backup cron (`backup.sh`, nice/ionice throttled)
- Monthly SSL certificate renewal cron (1st of month, 03:00 AM)

After deploy, the app is accessible at:
- `https://armguard.local` — via mDNS on any LAN device (Windows/Linux/macOS)
- `https://YOUR_LAN_IP` — direct IP fallback

---

## Step-by-Step Deployment

### Step 0 — Set a static LAN IP (optional)

> Skip if the server already has a fixed IP or a router DHCP reservation.

```bash
# Interactive — prompts for IP, gateway, DNS
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/set-static-ip.sh

# Non-interactive
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/set-static-ip.sh \
  --ip 192.168.0.11 --gateway 192.168.0.1

# Preview without applying
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/set-static-ip.sh --dry-run
```

The script backs up existing netplan config, writes the new one, and runs `netplan apply`. Verify with `ip a`.

---

### Step 1 — SSH into the Ubuntu server

```bash
ssh your_user@YOUR_SERVER_IP
```

---

### Step 2 — Install Git and clone the repo

```bash
sudo apt update && sudo apt install git -y

sudo git clone https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git \
  /var/www/ARMGUARD_RDS_V1
```

> **Private repo?** Use a personal access token:
> ```bash
> sudo git clone https://YOUR_TOKEN@github.com/september192016143-cyber/ARMGUARD_RDS_V1.git \
>   /var/www/ARMGUARD_RDS_V1
> ```

---

### Step 3 — Run the deploy script

Replace `192.168.0.11` with your server's actual LAN IP.

```bash
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/deploy.sh --domain armguard.local --lan-ip 192.168.0.11
```

To set a static IP and deploy in one go:

```bash
sudo bash scripts/deploy.sh \
  --static-ip 192.168.0.11 --gateway 192.168.0.1 \
  --domain armguard.local --lan-ip 192.168.0.11
```

**What the script configures automatically:**

| Item | Value |
|---|---|
| System user | `armguard` |
| Python venv | `/var/www/ARMGUARD_RDS_V1/venv/` |
| Gunicorn service | `armguard-gunicorn` (systemd) |
| Worker count | Auto-tuned by `gunicorn-autoconf.sh` (CPUs×2+1, capped by RAM) |
| Nginx site | `/etc/nginx/sites-available/armguard` |
| Self-signed SSL | `/etc/ssl/certs/armguard-selfsigned.crt` (SAN: LAN IP + `armguard.local`) |
| Avahi mDNS | Hostname set to `armguard`; broadcasts `armguard.local` on the LAN |
| Firewall | UFW: 22/tcp, 80/tcp, 443/tcp, 5353/udp open; 8000/tcp denied |
| Fail2Ban | SSH + Nginx jails enabled |
| Backup crons | Daily DB (02:00 AM) + every-3-hour full backup |
| Log rotation | `/etc/logrotate.d/armguard` — 14-day rolling |

---

### Step 4 — Review `.env` and create the superuser

```bash
# Confirm generated secrets look correct
sudo cat /var/www/ARMGUARD_RDS_V1/.env

# Edit if needed (ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, admin URL, etc.)
sudo nano /var/www/ARMGUARD_RDS_V1/.env

# Create the Django admin account
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
  /var/www/ARMGUARD_RDS_V1/project/manage.py createsuperuser
```

---

### Step 5 — Verify everything is running

```bash
# Both services should show "active (running)"
sudo systemctl status armguard-gunicorn
sudo systemctl status nginx

# Quick HTTP check from the server itself
curl -I http://127.0.0.1

# Live application log
sudo tail -f /var/log/armguard/gunicorn.log
```

Open a browser and navigate to `https://armguard.local` (or `https://YOUR_LAN_IP`) — the login page should appear.

---

### Step 6 — Enable HTTPS (self-signed SSL, LAN-only)

`deploy.sh` already generates the certificate and deploys the SSL Nginx config. Enable the HTTPS security flags in `.env`:

```bash
sudo nano /var/www/ARMGUARD_RDS_V1/.env
```

Set these values (use your actual LAN IP and/or `armguard.local`):

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://armguard.local,https://192.168.0.11
```

Restart Gunicorn to apply:

```bash
sudo systemctl restart armguard-gunicorn
```

**Trust the cert on Windows** so the browser shows a green padlock:

1. Browse to `https://armguard.local/download/ssl-cert/` — the app serves the `.crt` as a download.
2. Double-click the file → **Install Certificate** → **Local Machine** → **Trusted Root Certification Authorities**.
3. Restart Chrome/Edge completely.

Or via PowerShell (as Administrator) on your Windows PC:

```powershell
scp rds@192.168.0.11:/etc/ssl/certs/armguard-selfsigned.crt "$env:USERPROFILE\Desktop\armguard.crt"
certutil -addstore "Root" "$env:USERPROFILE\Desktop\armguard.crt"
```

Full guide: [`scripts/SSL_SELFSIGNED.md`](scripts/SSL_SELFSIGNED.md)

---

### Step 6b — WireGuard VPN (optional — off-LAN access)

```bash
# Set up WireGuard server once
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/setup-wireguard.sh

# For remote (off-LAN) access, pass your public IP
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/setup-wireguard.sh --server-ip <PUBLIC_IP>

# Copy client config to your PC (Windows PowerShell)
scp rds@192.168.0.11:/etc/wireguard/peers/peer1.conf "$env:USERPROFILE\Desktop\armguard-vpn.conf"

# Add more peers later
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/add-wireguard-peer.sh --name laptop
```

Import `armguard-vpn.conf` in the WireGuard app (Windows/Linux) or scan the printed QR code (Android/iOS).

---

### Step 7 — Future updates (pull latest code)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/update-server.sh
```

The script: pulls git, updates pip deps, runs migrations, re-tunes Gunicorn workers, collects static files, reloads Gunicorn zero-downtime, then verifies the health check endpoint returns HTTP 200.

---

## Deployment Artifacts

| File | Purpose |
|---|---|
| [`scripts/deploy.sh`](scripts/deploy.sh) | One-shot deploy — idempotent, safe to re-run |
| [`scripts/update-server.sh`](scripts/update-server.sh) | Pull latest code + zero-downtime Gunicorn reload |
| [`scripts/gunicorn.conf.py`](scripts/gunicorn.conf.py) | Gunicorn worker/thread/timeout config |
| [`scripts/gunicorn-autoconf.sh`](scripts/gunicorn-autoconf.sh) | Auto-tunes worker count based on CPU/RAM |
| [`scripts/armguard-gunicorn.service`](scripts/armguard-gunicorn.service) | systemd service unit |
| [`scripts/nginx-armguard.conf`](scripts/nginx-armguard.conf) | Nginx config (HTTP → HTTPS redirect + rate-limiting) |
| [`scripts/nginx-armguard-ssl-lan.conf`](scripts/nginx-armguard-ssl-lan.conf) | Nginx SSL config for LAN self-signed cert |
| [`scripts/avahi-daemon.conf`](scripts/avahi-daemon.conf) | Hardened Avahi mDNS config (IPv6 off, no workstation/OS fingerprinting) |
| [`scripts/setup-firewall.sh`](scripts/setup-firewall.sh) | UFW + Fail2Ban + unattended-upgrades setup |
| [`scripts/setup-wireguard.sh`](scripts/setup-wireguard.sh) | WireGuard VPN server setup (optional, for off-LAN access) |
| [`scripts/add-wireguard-peer.sh`](scripts/add-wireguard-peer.sh) | Add a WireGuard VPN client peer |
| [`scripts/set-static-ip.sh`](scripts/set-static-ip.sh) | Configure a static LAN IP via netplan |
| [`scripts/backup.sh`](scripts/backup.sh) | Full backup: DB + media + .env, optional GPG, external drive sync |
| [`scripts/db-backup-cron.sh`](scripts/db-backup-cron.sh) | Lightweight cron wrapper for Django `db_backup` management command |
| [`scripts/renew-ssl-cert.sh`](scripts/renew-ssl-cert.sh) | Monthly self-signed SSL certificate renewal (checks expiry first) |
| [`scripts/DEPLOY_GUIDE.md`](scripts/DEPLOY_GUIDE.md) | Full step-by-step deployment playbook with troubleshooting |
| [`scripts/SSL_SELFSIGNED.md`](scripts/SSL_SELFSIGNED.md) | Self-signed SSL guide + Windows cert import instructions |
| [`scripts/GOOGLE_SHEETS_SETUP.md`](scripts/GOOGLE_SHEETS_SETUP.md) | Google Sheets import integration guide |
| [`scripts/upload-sa-key.ps1`](scripts/upload-sa-key.ps1) | Upload Google service-account JSON key from Windows to server |
| [`Dockerfile`](Dockerfile) | Multi-stage Docker image (builder + runtime) |
| [`docker-compose.yml`](docker-compose.yml) | Docker Compose for local development |

---

## Key Paths (on-server)

| Path | Description |
|---|---|
| `/var/www/ARMGUARD_RDS_V1/` | Application root |
| `/var/www/ARMGUARD_RDS_V1/project/` | Django project root (`manage.py` lives here) |
| `/var/www/ARMGUARD_RDS_V1/.env` | Environment secrets (never commit to git) |
| `/var/www/ARMGUARD_RDS_V1/venv/` | Python virtual environment |
| `/var/www/ARMGUARD_RDS_V1/cache/` | FileBasedCache directory (shared by all Gunicorn workers) |
| `/var/log/armguard/` | Gunicorn + backup + SSL renewal logs |
| `/var/backups/armguard/` | Local backup snapshots (7-day rolling) |
| `/mnt/backup/armguard/` | External drive backup mirror (when mounted) |
| `/etc/gunicorn/workers.env` | Auto-tuned worker count (written by `gunicorn-autoconf.sh`) |
| `/etc/avahi/avahi-daemon.conf` | Hardened Avahi mDNS configuration |
| `/etc/ssl/certs/armguard-selfsigned.crt` | Self-signed SSL certificate (served as in-app download) |
| `/etc/ssl/private/armguard-selfsigned.key` | SSL private key (root-readable only, `chmod 600`) |
| `/etc/ssl/certs/dhparam.pem` | DH parameters for strong cipher suites |

---

## Environment Variables (`.env`)

`deploy.sh` generates `/var/www/ARMGUARD_RDS_V1/.env` automatically. Review it after deploy.

```env
# Django core
DJANGO_SECRET_KEY=<64-char random string — generated by deploy.sh>
DJANGO_SETTINGS_MODULE=armguard.settings.production
DJANGO_ALLOWED_HOSTS=armguard.local,192.168.0.11,localhost,127.0.0.1
DJANGO_ADMIN_URL=secure-admin-<random>/   # obfuscate the admin URL

# HTTPS (set to True once SSL is confirmed working)
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=31536000
CSRF_TRUSTED_ORIGINS=https://armguard.local,https://192.168.0.11

# SSL certificate path (used for the in-app cert download feature)
SSL_CERT_PATH=/etc/ssl/certs/armguard-selfsigned.crt

# Database (defaults to SQLite — no extra config needed)
# To use PostgreSQL, install psycopg2-binary and add:
# DATABASE_URL=postgres://armguard:STRONG_PASSWORD@localhost:5432/armguard_db

# Google Sheets import (optional)
# GOOGLE_SA_JSON=/var/www/armguard-sa.json

# Backup GPG encryption (optional — leave blank to skip)
ARMGUARD_BACKUP_GPG_RECIPIENT=
```

> `armguard.local` must be in `DJANGO_ALLOWED_HOSTS` for mDNS access to work.
> `CSRF_TRUSTED_ORIGINS` must include the `https://` scheme for CSRF to pass after SSL is enabled.

---

## Avahi mDNS (`armguard.local`)

`deploy.sh` installs and configures Avahi so any device on the LAN can reach the server at `armguard.local` without knowing its IP.

**What `deploy.sh` does:**

```bash
# Install packages
apt-get install avahi-daemon libnss-mdns

# Set server hostname
hostnamectl set-hostname armguard

# Install hardened config (disables IPv6, OS fingerprinting, workstation ads)
cp scripts/avahi-daemon.conf /etc/avahi/avahi-daemon.conf

# Enable and start
systemctl enable avahi-daemon
systemctl restart avahi-daemon
```

The SSL certificate is generated with `armguard.local` as a DNS SAN so the browser shows a valid padlock when the cert is trusted:

```
CN=armguard.local
SAN: IP:192.168.0.11, DNS:armguard.local
```

**`scripts/avahi-daemon.conf` settings:**
- `host-name=armguard` — broadcasts as `armguard.local`
- `use-ipv6=no` — LAN-only deployment, IPv6 disabled
- `publish-hinfo=no`, `publish-workstation=no` — no OS fingerprinting
- `enable-wide-area=no` — mDNS stays on local network only
- Resource limits set to minimal values

**Verify Avahi is running:**

```bash
systemctl status avahi-daemon
# From a Windows client:
ping armguard.local
```

**Firewall:** `setup-firewall.sh` opens `5353/udp` for mDNS multicast.

---

## Firewall Rules (UFW)

`deploy.sh` calls `scripts/setup-firewall.sh` to configure UFW. Additional rules are added by `setup-wireguard.sh` if WireGuard is set up.

| Port | Protocol | Rule | Purpose |
|---|---|---|---|
| 22 | TCP | Allow | SSH |
| 80 | TCP | Allow | HTTP (Nginx → HTTPS redirect) |
| 443 | TCP | Allow | HTTPS (Nginx + self-signed SSL) |
| 5353 | UDP | Allow | mDNS (Avahi — `armguard.local`) |
| 8000 | TCP | Deny | Block direct Gunicorn access |
| 51820 | UDP | Allow | WireGuard VPN (added by `setup-wireguard.sh`) |

Additional hardening installed by `setup-firewall.sh`:
- **Fail2Ban** — SSH brute-force (3 attempts → 24 h ban), Nginx 4xx/5xx ban
- **unattended-upgrades** — automatic security patches applied daily

---

## Font Awesome (Offline)

`deploy.sh` (step 7) and `update-server.sh` (step 4) both download Font Awesome 6.5.0 directly from cdnjs to the local static files directory, eliminating the CDN tracking-prevention warning browsers show for third-party requests.

Downloaded to: `project/armguard/static/css/fontawesome/` (CSS + webfonts)

The CSS SHA256 is verified against a known-good hash before use. If the hash mismatches, the file is deleted and a warning is printed — the app falls back to CDN gracefully.

---

## WireGuard VPN (Optional)

WireGuard provides encrypted off-LAN access so authorised users can reach the app remotely without exposing ports to the internet.

```bash
# Set up WireGuard server (run once on the server)
sudo bash scripts/setup-wireguard.sh

# Add a client peer (run for each remote user)
sudo bash scripts/add-wireguard-peer.sh --name john
```

`setup-wireguard.sh` opens UFW port `51820/udp` automatically.

See [`scripts/DEPLOY_GUIDE.md`](scripts/DEPLOY_GUIDE.md) (WireGuard section) for the full peer configuration workflow including generating client configs and QR codes.

---

## SSL Certificate (Self-Signed, LAN)

`deploy.sh` generates a 3-year self-signed certificate automatically if none exists:

```
/etc/ssl/certs/armguard-selfsigned.crt   (SAN: IP:<LAN_IP> + DNS:armguard.local)
/etc/ssl/private/armguard-selfsigned.key  (chmod 600)
/etc/ssl/certs/dhparam.pem                (2048-bit DH params)
```

**Enable HTTPS** by switching the Nginx config to `nginx-armguard-ssl-lan.conf` and setting in `.env`:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Then restart Gunicorn: `sudo systemctl restart armguard-gunicorn`

**Trust the cert on Windows** (eliminates the browser warning permanently):

1. Browse to `https://armguard.local/download/ssl-cert/` — the app serves the `.crt` as a download.
2. Double-click the downloaded file → **Install Certificate** → **Local Machine** → **Trusted Root Certification Authorities**.
3. Restart Chrome/Edge completely.

Full guide: [`scripts/SSL_SELFSIGNED.md`](scripts/SSL_SELFSIGNED.md)

**Monthly auto-renewal cron** (installed by `deploy.sh`):

```
0 3 1 * * /var/www/ARMGUARD_RDS_V1/scripts/renew-ssl-cert.sh >> /var/log/armguard/ssl-renewal.log 2>&1
```

Renews only if the certificate expires within 45 days — safe to run every month.

---

## Backup Strategy

Two cron jobs are installed by `deploy.sh`:

| Script | Schedule | What it backs up |
|---|---|---|
| `db-backup-cron.sh` | Daily 02:00 AM (as `armguard` user) | Database via Django `db_backup` management command |
| `backup.sh` | Every 3 hours (as root, nice/ionice throttled) | DB + `media/` + `.env`, optional GPG encryption, external drive sync |

Backups are stored at `/var/backups/armguard/` with 7-day rolling retention. If `/mnt/backup/` is mounted, backups are also synced there via `rsync`.

**Verify backups:**

```bash
tail -f /var/log/armguard/backup.log
ls /var/backups/armguard/
```

**Restore a backup:**

```bash
ls /var/backups/armguard/          # list snapshots

# Restore DB (replace TIMESTAMP)
sudo systemctl stop armguard-gunicorn
cp /var/backups/armguard/TIMESTAMP/db.sqlite3 /var/www/ARMGUARD_RDS_V1/project/db.sqlite3
sudo systemctl start armguard-gunicorn
```

---

## Log Rotation

`deploy.sh` installs `/etc/logrotate.d/armguard`:
- Rotates `/var/log/armguard/*.log` daily
- Keeps 14 days of compressed history
- Sends reload signal to Gunicorn after rotation so it reopens file handles

**Test the config:**

```bash
sudo logrotate --debug /etc/logrotate.d/armguard
```

**Application logs** (Django) are written to `/var/www/ARMGUARD_RDS_V1/project/logs/armguard.log` via the `RotatingFileHandler` (5 MB max, 5 backups). Three log namespaces:

| Logger | Level | Content |
|---|---|---|
| `armguard` | WARNING | General application warnings/errors |
| `armguard.transactions` | INFO | Every Withdrawal and Return event |
| `armguard.audit` | INFO | Post-save/delete signals for inventory and personnel models |
| `armguard.system` | INFO | Startup, backups, session cleanup, management commands (written by `log_system_event()`) |
| `django.security` | WARNING | Django security framework events |

---

## SystemLog Model

The `SystemLog` model (`armguard.apps.users.models`) records infrastructure-level events that don't belong in the user-facing `AuditLog`. Use `log_system_event()` from any management command, signal handler, or app ready hook:

```python
from armguard.apps.users.models import log_system_event

log_system_event(
    source='BACKUP',         # STARTUP | BACKUP | MIGRATION | SESSION | COMMAND | CACHE | EMAIL | FILE | SCHEDULER | OTHER
    event='backup_created',  # short snake_case event name
    message='Daily backup complete',
    level='INFO',            # INFO | WARNING | ERROR | CRITICAL
    file='/var/backups/armguard/20260101_020000.tar.gz',
    size_mb=12.4,
)
```

Events are viewable in Django Admin → **System Logs** with coloured level/source badges and a filterable sidebar.

---

## PostgreSQL Migration (Optional)

SQLite is the default and works well for single-server, low-concurrency deployments. To migrate to PostgreSQL:

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y
sudo -u postgres createuser armguard
sudo -u postgres createdb armguard_db -O armguard
sudo -u postgres psql -c "ALTER USER armguard PASSWORD 'STRONG_PASSWORD';"

# Export existing data from SQLite
cd /var/www/ARMGUARD_RDS_V1/project
source ../venv/bin/activate
python manage.py dumpdata --natural-foreign --natural-primary \
  --exclude=contenttypes --exclude=auth.permission \
  -o /tmp/armguard_data.json

# Add psycopg2 to requirements and install
sed -i 's/# psycopg2-binary/psycopg2-binary/' /var/www/ARMGUARD_RDS_V1/requirements.txt
pip install psycopg2-binary

# Add to .env
echo "DATABASE_URL=postgres://armguard:STRONG_PASSWORD@localhost:5432/armguard_db" \
  >> /var/www/ARMGUARD_RDS_V1/.env

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

# Pull updates and restart (zero-downtime)
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/update-server.sh

# Run Django migrations after update
cd /var/www/ARMGUARD_RDS_V1/project
sudo -u armguard ../venv/bin/python manage.py migrate

# Collect static files after update
sudo -u armguard ../venv/bin/python manage.py collectstatic --noinput

# Check for security regressions
sudo -u armguard ../venv/bin/python manage.py check --deploy

# Re-tune Gunicorn worker count (e.g. after hardware change)
sudo bash /usr/local/bin/gunicorn-autoconf.sh
sudo systemctl restart armguard-gunicorn

# View Avahi mDNS status
systemctl status avahi-daemon

# View SystemLog events in the shell
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
  /var/www/ARMGUARD_RDS_V1/project/manage.py shell -c \
  "from armguard.apps.users.models import SystemLog; \
   [print(e.timestamp, e.level, e.source, e.event) for e in SystemLog.objects.order_by('-timestamp')[:20]]"
```
