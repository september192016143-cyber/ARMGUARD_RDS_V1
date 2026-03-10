# ARMGUARD RDS V1 — Production Deployment Guide

> Target OS: Ubuntu Server 24.04 LTS  
> Deploy path: `/var/www/ARMGUARD_RDS_V1`  
> GitHub: `https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git`

---

## Prerequisites

- Ubuntu Server 24.04 LTS (VPS or bare metal)
- Static IP or domain name pointed at the server
- SSH root or sudo access
- Internet access to pull from GitHub

---

## STEP 1 — SSH into the Ubuntu server

```bash
ssh your_user@YOUR_SERVER_IP
```

---

## STEP 2 — Install Git and clone the repo

```bash
sudo apt update && sudo apt install git -y

sudo git clone https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git /var/www/ARMGUARD_RDS_V1
```

> **Private repo?** Use a personal access token instead:
> ```bash
> sudo git clone https://YOUR_GITHUB_TOKEN@github.com/september192016143-cyber/ARMGUARD_RDS_V1.git /var/www/ARMGUARD_RDS_V1
> ```

---

## STEP 3 — Run the deploy script

This single command installs all system packages, creates the `armguard` system user, sets up the Python virtual environment, generates the `.env` file, runs database migrations, collects static files, installs Gunicorn as a systemd service, configures Nginx, enables the UFW firewall, and sets up log rotation.

```bash
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/deploy.sh --domain YOUR_SERVER_IP --lan-ip YOUR_LAN_IP
```

Replace:
- `YOUR_SERVER_IP` — public IP of the server (e.g. `192.168.1.50`)
- `YOUR_LAN_IP` — LAN IP if behind a router (e.g. `192.168.1.50`); same value is fine for single-NIC setups

If you have a real domain name, use `--domain yourdomain.com`.

**What the script sets up automatically:**

| Item | Value |
|---|---|
| System user | `armguard` |
| Deploy path | `/var/www/ARMGUARD_RDS_V1` |
| Python venv | `/var/www/ARMGUARD_RDS_V1/venv` |
| Gunicorn service | `armguard-gunicorn` (systemd) |
| Nginx site | `/etc/nginx/sites-available/armguard` |
| Log directory | `/var/log/armguard/` |
| Firewall | UFW: ports 22, 80, 443 open; 8000 blocked |

---

## STEP 4 — Create the superuser (admin account)

```bash
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
  /var/www/ARMGUARD_RDS_V1/project/manage.py createsuperuser
```

Follow the prompts — set a username, email, and strong password.

---

## STEP 5 — Verify everything is running

```bash
# Check both services are active (green)
sudo systemctl status armguard-gunicorn
sudo systemctl status nginx

# Test HTTP response from the server itself
curl -I http://YOUR_SERVER_IP

# Watch live application logs
sudo tail -f /var/log/armguard/gunicorn.log
```

Open a browser and navigate to `http://YOUR_SERVER_IP` — the login page should appear.

---

## STEP 6 — Add SSL with Certbot (recommended)

> Only do this if you have a real domain name pointed at this server's public IP.

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com
```

Certbot will automatically configure Nginx for HTTPS and schedule auto-renewal.

After SSL is confirmed working, **enable the HTTPS security flags** in `.env`:

```bash
sudo nano /var/www/ARMGUARD_RDS_V1/.env
```

Change these four lines from `False` / plain HTTP to the values below:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://yourdomain.com
```

Restart Gunicorn to apply:

```bash
sudo systemctl restart armguard-gunicorn
```

---

## STEP 6b — Self-Signed SSL for LAN-Only (No Public Domain)

> Use this instead of Step 6 when the server has **no domain name** and is only accessible inside the local network (e.g. `192.168.0.11`).

### Part 1 — Generate the certificate on the server

Run this on the **Ubuntu server** (replace `192.168.0.11` with your server's LAN IP):

```bash
sudo openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
  -keyout /etc/ssl/private/armguard-selfsigned.key \
  -out /etc/ssl/certs/armguard-selfsigned.crt \
  -subj "/C=PH/ST=Metro Manila/L=Manila/O=ArmGuard RDS/CN=192.168.0.11" \
  -addext "subjectAltName=IP:192.168.0.11"
```

> The `-addext "subjectAltName=..."` flag is **required** — without it, Chrome and modern browsers will still show "Not secure" even after importing the cert.

### Part 2 — Apply the SSL Nginx config

```bash
sudo cp /var/www/ARMGUARD_RDS_V1/scripts/nginx-armguard-ssl-lan.conf \
  /etc/nginx/sites-available/armguard

sudo nginx -t && sudo systemctl reload nginx
```

### Part 3 — Enable HTTPS flags in `.env`

```bash
sudo nano /var/www/ARMGUARD_RDS_V1/.env
```

Update these lines (replace the IP with your actual server IP):

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://192.168.0.11
```

Restart Gunicorn to apply:

```bash
sudo systemctl restart armguard-gunicorn
```

### Part 4 — Import the certificate into Windows (eliminates "Not secure" warning)

> Run these commands on your **Windows PC**, not the server. Open **Windows PowerShell** (not the SSH terminal).

**Step 4a — Copy the cert from the server to your Desktop:**

```powershell
scp rds@192.168.0.11:/etc/ssl/certs/armguard-selfsigned.crt "$env:USERPROFILE\Desktop\armguard.crt"
```

**Step 4b — Import the cert as a Trusted Root CA (open PowerShell as Administrator):**

```powershell
certutil -addstore "Root" "$env:USERPROFILE\Desktop\armguard.crt"
```

**Step 4c — Close and reopen Chrome completely** (all windows, or use `chrome://restart`).

Navigate to `https://192.168.0.11` — the padlock should now be green with no "Not secure" warning.

> **Before renewing the certificate**, remove the old one first:
> ```powershell
> certutil -delstore "Root" "ArmGuard RDS"
> ```
> Then repeat Steps 4a–4c with the new cert.

---

## STEP 7 — Future updates (pull latest code)

Every time you push new commits from your development machine, update the server with:

```bash
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/update-server.sh --branch main
```

This pulls the latest commit, re-installs any new dependencies, runs new migrations, re-collects static files, and gracefully restarts Gunicorn.

---

## Service Management Quick Reference

```bash
# Restart application
sudo systemctl restart armguard-gunicorn

# Reload Nginx config (zero downtime)
sudo systemctl reload nginx

# Live application logs
sudo journalctl -u armguard-gunicorn -f

# Live Nginx error log
sudo tail -f /var/log/nginx/error.log

# Manual database backup
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
  /var/www/ARMGUARD_RDS_V1/project/manage.py db_backup --keep 14
```

---

## Environment Variables Reference

Location: `/var/www/ARMGUARD_RDS_V1/.env`

| Variable | Required | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | ✅ Yes | 64-char random string — auto-generated by `deploy.sh` |
| `DJANGO_DEBUG` | ✅ Yes | Must be `False` in production |
| `DJANGO_ALLOWED_HOSTS` | ✅ Yes | Comma-separated: `domain.com,192.168.1.100` |
| `DJANGO_ADMIN_URL` | ⚠️ Recommended | Custom admin path (default: `admin/`) |
| `CSRF_TRUSTED_ORIGINS` | ✅ Yes | `https://domain.com,http://192.168.1.100` |
| `SECURE_SSL_REDIRECT` | ⚠️ After SSL | Set `True` once HTTPS is confirmed working |
| `SECURE_HSTS_SECONDS` | ✅ Yes | `31536000` (1 year) |
| `SESSION_COOKIE_SECURE` | ⚠️ After SSL | Set `True` once HTTPS is confirmed working |
| `CSRF_COOKIE_SECURE` | ⚠️ After SSL | Set `True` once HTTPS is confirmed working |

---

## Deployment Directory Layout

```
/var/www/ARMGUARD_RDS_V1/
├── .env                    # Production environment variables (chmod 600)
├── requirements.txt
├── venv/                   # Python virtual environment
├── backups/                # SQLite hot-copy backup files
├── scripts/                # Deployment scripts
└── project/                # Django project root
    ├── manage.py
    ├── db.sqlite3          # Database (chmod 600, owned by armguard)
    ├── staticfiles/        # collectstatic output (served by Nginx)
    ├── media/              # User-uploaded files (served by Nginx)
    └── armguard/
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

## Troubleshooting

| Symptom | Command to run |
|---|---|
| Service fails to start | `sudo journalctl -u armguard-gunicorn -n 50 --no-pager` |
| 502 Bad Gateway | `sudo systemctl status armguard-gunicorn` |
| Static files not loading | `sudo systemctl reload nginx` |
| Permission denied errors | `sudo chown -R armguard:armguard /var/www/ARMGUARD_RDS_V1` |
| Login CSRF error | Check `CSRF_TRUSTED_ORIGINS` in `.env` |
| SSL redirect loop | Confirm Nginx has HTTPS, then set `SECURE_SSL_REDIRECT=True` in `.env` |

---

## What's Already Hardened in the Codebase

| Feature | Detail |
|---|---|
| SQLite WAL mode | Activated on every connection via Django signal — survives concurrent Gunicorn workers |
| Nginx upstream keepalive | Pool of 8 persistent connections — fewer TCP handshakes |
| Nginx gzip | Enabled for HTML/JSON responses — faster page loads |
| HTTPS flags off by default | `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` all default `False` — login works on HTTP-only until SSL is confirmed |
| CSP enforced | `script-src 'self'` — no inline scripts allowed |
| Secrets in `.env` | `SECRET_KEY` and all sensitive flags are never committed to git |
| LF line endings | `.gitattributes` enforces LF for all shell scripts — no `bad interpreter` errors on Ubuntu |
