# ARMGUARD RDS V1 — Deployment Scripts

Scripts for deploying and maintaining **ARMGUARD RDS V1** on Ubuntu Server 24.04 LTS (HP ProDesk Mini).

---

## Scripts Overview

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Full first-time deployment orchestrator |
| `update-server.sh` | Pull latest code and hot-reload service |
| `armguard-gunicorn.service` | systemd unit file for Gunicorn |
| `nginx-armguard.conf` | Nginx reverse proxy configuration |
| `setup-firewall.sh` | UFW firewall rules |
| `db-backup-cron.sh` | Cron wrapper for daily SQLite backup |

---

## Quick Start

### First Deployment

```bash
# 1. Copy project to the server
scp -r ARMGUARD_RDS_V1/ user@server-ip:~/

# 2. SSH into server
ssh user@server-ip

# 3. Run the deployment script as root
cd ~/ARMGUARD_RDS_V1
sudo bash scripts/deploy.sh --domain armguard.local --lan-ip 192.168.1.100
```

For non-interactive / scripted deployment:

```bash
sudo bash scripts/deploy.sh --quick --domain 192.168.1.100 --lan-ip 192.168.1.100
```

After deployment:

```bash
# Create the first superuser account
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
    /var/www/ARMGUARD_RDS_V1/project/manage.py createsuperuser
```

---

## Script Details

### `deploy.sh`

Full deployment from scratch. Run once on a fresh Ubuntu 24.04 system.

**What it does:**
1. Validates OS and root privileges
2. Installs system packages (Python 3.12, Nginx, image libraries, etc.)
3. Creates `armguard` system user
4. Copies project files to `/var/www/armguard-v1/`
5. Creates Python virtual environment and installs `requirements.txt`
6. Generates `/var/www/armguard-v1/.env` with a random secret key
7. Runs Django migrations and `collectstatic`
8. Installs and starts systemd service (`armguard-gunicorn`)
9. Configures Nginx
10. Configures UFW firewall
11. Sets up log rotation and backup cron

**Options:**

| Option | Description |
|--------|-------------|
| `--quick` | Skip confirmation prompts |
| `--production` | Enable production hardening mode |
| `--domain DOMAIN` | Server domain or IP |
| `--lan-ip IP` | LAN IP to bind Nginx |
| `--help` | Show usage |

---

### `update-server.sh`

Zero-downtime update: pull latest code, migrate, collectstatic, graceful reload.

```bash
# Standard update (interactive confirmation)
sudo bash scripts/update-server.sh

# Quick update on specific branch
sudo bash scripts/update-server.sh --branch main --quick

# Only reload service, skip git/pip
sudo bash scripts/update-server.sh --skip-migrate --skip-static
```

**Options:**

| Option | Description |
|--------|-------------|
| `--skip-migrate` | Skip `manage.py migrate` |
| `--skip-static` | Skip `manage.py collectstatic` |
| `--no-restart` | Don't restart Gunicorn after update |
| `--branch BRANCH` | Git branch to pull (default: `main`) |

The script creates a pre-update backup before making any changes.

---

### `armguard-gunicorn.service`

systemd unit file for Gunicorn. Installed automatically by `deploy.sh`.

**Manual installation:**

```bash
# 1. Edit paths if different from /var/www/armguard-v1
# 2. Install
sudo cp scripts/armguard-gunicorn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable armguard-gunicorn
sudo systemctl start armguard-gunicorn

# 3. Check status
sudo systemctl status armguard-gunicorn
sudo journalctl -u armguard-gunicorn -f
```

**Worker count:** The service uses 2 workers by default, suited for a 2–4 core HP ProDesk Mini with SQLite. Increase to 3–4 if you migrate to PostgreSQL.

---

### `nginx-armguard.conf`

Nginx configuration with:
- Static file serving (bypasses Gunicorn)
- Media file serving (with script-execution blocked on uploaded files)
- Login endpoint rate limiting (5 requests/minute)
- Security: hides Nginx version, blocks dotfiles and sensitive extensions
- Commented-out HTTPS block (enable after obtaining SSL certificate)

**Manual installation:**

```bash
# Install configuration
sudo cp scripts/nginx-armguard.conf /etc/nginx/sites-available/armguard

# Edit domain/IP placeholders
sudo nano /etc/nginx/sites-available/armguard

# Enable
sudo ln -s /etc/nginx/sites-available/armguard /etc/nginx/sites-enabled/armguard
sudo rm -f /etc/nginx/sites-enabled/default

# Create proxy-params snippet (if not present)
sudo tee /etc/nginx/snippets/proxy-params.conf <<'EOF'
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_redirect    off;
proxy_buffering   off;
EOF

sudo nginx -t && sudo systemctl reload nginx
```

**Adding SSL (Let's Encrypt):**

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# Enable SECURE_SSL_REDIRECT in .env after SSL is working
sudo nano /var/www/armguard-v1/.env
# Set: SECURE_SSL_REDIRECT=True

# Reload service
sudo systemctl reload armguard-gunicorn
```

---

### `setup-firewall.sh`

Configures UFW with minimal necessary rules.

```bash
# Standard firewall setup
sudo bash scripts/setup-firewall.sh

# With custom SSH port
sudo bash scripts/setup-firewall.sh --ssh-port 2222

# Allow all traffic from LAN
sudo bash scripts/setup-firewall.sh --allow-lan 192.168.1.0/24

# Check current rules
sudo bash scripts/setup-firewall.sh --status
```

**Rules applied:**

| Port/Protocol | Action | Reason |
|--------------|--------|--------|
| 22/tcp | ALLOW | SSH access |
| 80/tcp | ALLOW | HTTP (Nginx) |
| 443/tcp | ALLOW | HTTPS (Nginx) |
| 8000/tcp | DENY | Block direct Gunicorn access |
| All else | DENY | Default deny incoming |

---

### `db-backup-cron.sh`

Wrapper for `manage.py db_backup`. Creates a safe hot-copy SQLite backup using Python's `sqlite3.Connection.backup()`.

**Setup:**

```bash
# Install cron job for armguard user (daily at 2 AM)
sudo crontab -u armguard -e
# Add:
# 0 2 * * * /var/www/armguard-v1/scripts/db-backup-cron.sh >> /var/log/armguard/backup.log 2>&1
```

**Manual run:**

```bash
sudo bash scripts/db-backup-cron.sh
```

Backups are stored in `/var/www/armguard-v1/backups/`. 14 daily backups are retained (configurable via `KEEP_DAYS`).

---

## Service Management

```bash
# Status
sudo systemctl status armguard-gunicorn
sudo systemctl status nginx

# Logs (live)
sudo journalctl -u armguard-gunicorn -f
sudo tail -f /var/log/armguard/gunicorn.log
sudo tail -f /var/log/nginx/access.log

# Restart
sudo systemctl restart armguard-gunicorn
sudo systemctl reload nginx

# Graceful reload (zero-downtime)
sudo systemctl reload armguard-gunicorn
```

---

## Management Commands

```bash
PYTHON="/var/www/armguard-v1/venv/bin/python"
MANAGE="$PYTHON /var/www/armguard-v1/project/manage.py"
DJANGO_SETTINGS_MODULE=armguard.settings.production

# Cleanup expired sessions
sudo -u armguard $MANAGE cleanup_sessions --delete

# Export audit log (last 30 days)
sudo -u armguard $MANAGE export_audit_log --days 30 --output /tmp/audit.csv

# Manual database backup
sudo -u armguard $MANAGE db_backup --keep 14

# Django system check
sudo -u armguard $MANAGE check --deploy
```

---

## Deployment Directory Layout

```
/var/www/armguard-v1/
├── .env                    # Production environment variables (chmod 600)
├── requirements.txt
├── venv/                   # Python virtual environment
├── backups/                # SQLite backup files
├── scripts/                # Deployment scripts (this folder)
└── project/                # Django project root
    ├── manage.py
    ├── db.sqlite3          # Database (chmod 600, owned by armguard)
    ├── staticfiles/        # collectstatic output (served by Nginx)
    ├── media/              # User-uploaded files (served by Nginx)
    └── armguard/           # Django settings, URLs, WSGI
        └── settings/
            ├── base.py
            └── production.py

/var/log/armguard/
├── gunicorn.log
├── gunicorn-access.log
└── backup.log

/etc/systemd/system/
└── armguard-gunicorn.service

/etc/nginx/
├── sites-available/armguard
└── sites-enabled/armguard  → sites-available/armguard
```

---

## Environment Variables (.env)

Key variables in `/var/www/armguard-v1/.env`:

| Variable | Required | Notes |
|----------|----------|-------|
| `DJANGO_SECRET_KEY` | ✅ Yes | 64-char random string (auto-generated by deploy.sh) |
| `DJANGO_DEBUG` | ✅ Yes | Must be `False` in production |
| `DJANGO_ALLOWED_HOSTS` | ✅ Yes | Comma-separated: `domain.com,192.168.1.100` |
| `DJANGO_ADMIN_URL` | ⚠️ Recommended | Custom admin path (default: `admin`) |
| `CSRF_TRUSTED_ORIGINS` | ✅ Yes | `https://domain.com,http://192.168.1.100` |
| `SECURE_SSL_REDIRECT` | ⚠️ After SSL | Set `True` once HTTPS is working |
| `SECURE_HSTS_SECONDS` | ✅ Yes | `31536000` (1 year) |
| `SESSION_COOKIE_SECURE` | ✅ After SSL | Set `True` once HTTPS is working |
| `CSRF_COOKIE_SECURE` | ✅ After SSL | Set `True` once HTTPS is working |

---

## Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u armguard-gunicorn -n 50 --no-pager
# Common causes: wrong WSGI path, missing .env, bad SECRET_KEY
```

**502 Bad Gateway from Nginx:**
```bash
sudo systemctl status armguard-gunicorn
# Gunicorn is likely not running. Check logs above.
```

**Static files not served:**
```bash
sudo -u armguard /var/www/armguard-v1/venv/bin/python \
    /var/www/armguard-v1/project/manage.py collectstatic --noinput
sudo nginx -t && sudo systemctl reload nginx
```

**Permission errors:**
```bash
sudo chown -R armguard:armguard /var/www/armguard-v1
sudo chown -R armguard:armguard /var/log/armguard
```
