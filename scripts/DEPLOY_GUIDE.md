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

## STEP 0 — Set a static IP on the server (LAN deployments)

> Skip this step if the server already has a static IP or is assigned a fixed lease by your router.

After cloning the repo (Step 2), run the static IP script:

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/set-static-ip.sh
```

You will be prompted for the IP, gateway, and DNS — or pass them directly:

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/set-static-ip.sh \
  --ip 192.168.0.11 \
  --gateway 192.168.0.1
```

To preview without applying:

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/set-static-ip.sh --dry-run
```

> The script backs up existing netplan files before writing, then runs `netplan apply`. Verify with `ip a` after it completes.

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
sudo bash scripts/deploy.sh --domain 192.168.0.11 --lan-ip 192.168.0.11
```

Replace `192.168.0.11` with your actual server LAN IP. If you have a real domain name, use `--domain yourdomain.com`.

**One-liner: set static IP and deploy at the same time:**

```bash
# Uses 192.168.0.11, derives gateway 192.168.0.1 automatically
sudo bash scripts/deploy.sh --static-ip 192.168.0.11 --lan-ip 192.168.0.11 --domain 192.168.0.11

# With explicit gateway
sudo bash scripts/deploy.sh --static-ip 192.168.0.11 --gateway 192.168.0.1 --lan-ip 192.168.0.11 --domain 192.168.0.11
```

**What the script sets up automatically:**

| Item | Value |
|---|---|
| System user | `armguard` |
| Deploy path | `/var/www/ARMGUARD_RDS_V1` |
| Python venv | `/var/www/ARMGUARD_RDS_V1/venv` |
| Gunicorn config | `scripts/gunicorn.conf.py` (worker class, timeouts, limits) |
| Worker auto-tuner | `/usr/local/bin/gunicorn-autoconf.sh` — runs at deploy and every update |
| Worker env file | `/etc/gunicorn/workers.env` (written by auto-tuner) |
| Gunicorn service | `armguard-gunicorn` (systemd) |
| Nginx site | `/etc/nginx/sites-available/armguard` |
| Log directory | `/var/log/armguard/` |
| Firewall | UFW: ports 22, 80, 443, 51820/udp open; 8000 blocked |
| VPN | WireGuard on port 51820/udp — run `setup-wireguard.sh` after deploy |
| Fail2Ban | SSH jail (24 h ban) + Nginx jails — installed by `setup-firewall.sh` |
| Auto security patches | `unattended-upgrades` enabled — installed by `setup-firewall.sh` |

---

## STEP 4 — Create the superuser (admin account)

**First, check the generated `.env`** — confirm the secret key and settings look correct before creating the superuser:

```bash
# View it
sudo cat /var/www/ARMGUARD_RDS_V1/.env

# Edit if needed
sudo nano /var/www/ARMGUARD_RDS_V1/.env
```

Then create the admin account:

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
curl -I http://192.168.0.11

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

## STEP 6c — WireGuard VPN (optional — off-LAN access)

> Use this if you need to access ArmGuard from a device that is **not on the same LAN** as the server (e.g. a remote administrator or officer on a separate network).

### Part 1 — Run the setup script on the server

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/setup-wireguard.sh
```

What it does automatically:
- Installs WireGuard
- Generates server keypair and writes `/etc/wireguard/wg0.conf`
- Opens UFW port 51820/udp
- Regenerates the SSL cert with `10.8.0.1` as an additional IP SAN
- Updates `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` in `.env`
- Restarts Gunicorn
- Generates the first client config at `/etc/wireguard/peers/peer1.conf`
- Prints a QR code for mobile import

For remote access (client connects from outside the LAN), pass the public IP:

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/setup-wireguard.sh --server-ip <PUBLIC_IP>
```

### Part 2 — Copy the client config to your device

```bash
# From your PC (Windows PowerShell)
scp rds@192.168.0.11:/etc/wireguard/peers/peer1.conf "$env:USERPROFILE\Desktop\armguard-vpn.conf"
```

### Part 3 — Import and connect

- **Windows/Linux**: Open the WireGuard app → Import tunnel → select `armguard-vpn.conf` → Activate
- **Android/iOS**: Open the WireGuard app → scan the QR code printed by the setup script

### Part 4 — Access the app over VPN

Once connected, browse to `https://10.8.0.1` and install the SSL certificate if prompted.

### Adding more VPN clients later

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/add-wireguard-peer.sh --name laptop
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/add-wireguard-peer.sh --name iphone
```

---

## STEP 7 — Future updates (pull latest code)

Every time you push new commits from your development machine, update the server with:

```bash
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/update-server.sh

# Or target a specific branch explicitly
sudo bash scripts/update-server.sh --branch main
```

The script:
1. Creates a pre-update SQLite backup
2. Pulls latest commits from git
3. Updates pip dependencies
4. Runs new migrations
5. **Re-runs `gunicorn-autoconf.sh`** to recompute worker count
6. Collects static files
7. Gracefully reloads Gunicorn (zero downtime)
8. **Verifies `http://127.0.0.1:8000/health/`** returns HTTP 200 — catches broken deploys that systemd wouldn't detect

---

## Service Management Quick Reference

```bash
# Restart application
sudo systemctl restart armguard-gunicorn

# Reload Nginx config (zero downtime)
sudo systemctl reload nginx

# Rebuild static files manually (after template/CSS changes without a full update)
sudo bash -c "cd /var/www/ARMGUARD_RDS_V1/project && ../venv/bin/python manage.py collectstatic --noinput"

# Live application logs
sudo journalctl -u armguard-gunicorn -f

# Live Nginx error log
sudo tail -f /var/log/nginx/error.log

# Re-run worker auto-tuner (after hardware changes or manual override removal)
sudo /usr/local/bin/gunicorn-autoconf.sh
sudo systemctl reload armguard-gunicorn

# Preview auto-tuner without writing
sudo /usr/local/bin/gunicorn-autoconf.sh --dry-run

# Manual full backup (DB + media + .env)
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh

# Manual database-only backup (legacy)
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
| `CONN_MAX_AGE` | 🟢 Recommended | Persistent DB connections (e.g. `60`). Eliminates per-request connect overhead. |
| `GUNICORN_WORKERS` | 🟢 Optional | Override auto-tuned worker count. Normally written by `gunicorn-autoconf.sh`. |
| `GUNICORN_THREADS` | 🟢 Optional | Override auto-tuned thread count (2 = SSD, 4 = HDD). |
| `ARMGUARD_BACKUP_GPG_RECIPIENT` | 🟢 Optional | GPG key recipient for encrypted backups (e.g. `backup@example.com`). |

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
├── gunicorn-autoconf.log   # worker auto-tuner decisions
└── backup.log

/var/backups/armguard/
└── YYYYMMDD_HHMMSS/        # timestamped snapshots (7-day rotation)
    ├── db_<ts>.sqlite3
    ├── media_<ts>.tar.gz
    └── env_<ts>.env

/etc/gunicorn/
└── workers.env             # GUNICORN_WORKERS + GUNICORN_THREADS (written by autoconf)

/etc/systemd/system/
└── armguard-gunicorn.service

/etc/nginx/
├── sites-available/armguard
└── sites-enabled/armguard  → sites-available/armguard

/usr/local/bin/
└── gunicorn-autoconf.sh    # runtime worker auto-tuner (installed by deploy.sh)
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
| Wrong worker count | `sudo /usr/local/bin/gunicorn-autoconf.sh --dry-run` to inspect, then reload |
| Health check fails after update | App responded but `curl http://127.0.0.1:8000/health/` returned non-200 — check `journalctl -u armguard-gunicorn -n 50` |
| git pull blocked by ownership error | `sudo git config --global --add safe.directory /var/www/ARMGUARD_RDS_V1` |
| `.env` has bad chars / metacharacters | `sudo rm /var/www/ARMGUARD_RDS_V1/.env` then re-run `deploy.sh` — it regenerates a clean one |

---

## Repair / Re-deploy Cheatsheet

Use this when the server is in a broken state (bad `.env`, git ownership issue, corrupt install, etc.).

```bash
cd /var/www/ARMGUARD_RDS_V1

# 1. Fix git ownership (needed if root cloned the repo)
sudo git config --global --add safe.directory /var/www/ARMGUARD_RDS_V1

# 2. Pull latest code
sudo git pull origin main

# 3. If .env is corrupt / has metacharacters in the secret key — delete and regenerate
sudo rm /var/www/ARMGUARD_RDS_V1/.env

# 4. Re-run deploy — regenerates .env, re-runs migrations, restarts service
#    All existing data (database, media/, backups/) is preserved.
sudo bash scripts/deploy.sh --domain 192.168.0.11 --lan-ip 192.168.0.11

# 5. Review the generated .env
sudo cat /var/www/ARMGUARD_RDS_V1/.env
sudo nano /var/www/ARMGUARD_RDS_V1/.env   # edit if needed

# 6. Restart Gunicorn to pick up any .env changes
sudo systemctl restart armguard-gunicorn

# 7. Verify
sudo systemctl status armguard-gunicorn
sudo systemctl status nginx
curl -I http://192.168.0.11
```

> **Data safety on re-deploy:** `db.sqlite3`, `media/`, `.env` (if it exists), `backups/`, and the Nginx SSL config are all **skipped** — never overwritten. See the data safety table in the FAQ above.

---

## What's Already Hardened in the Codebase

| Feature | Detail |
|---|---|
| SQLite WAL mode | Activated on every connection via Django signal — survives concurrent Gunicorn workers |
| Gunicorn `gthread` workers | Each worker handles multiple requests concurrently; prevents a slow DB query from stalling the whole process |
| Worker auto-tuning | `gunicorn-autoconf.sh` computes `(CPUs×2)+1` workers capped by RAM at deploy and every update |
| Nginx upstream keepalive | Pool of 8 persistent connections — fewer TCP handshakes |
| Nginx `sendfile`/`tcp_nopush` | Zero-copy file kernel path enabled — faster static file delivery |
| Nginx gzip | Enabled for HTML/JSON responses — faster page loads |
| Nginx security headers | HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, CSP |
| `/health/` exempt from rate limit | Monitoring/load-balancer probes never trigger 429 |
| Fail2Ban | SSH (3 attempts → 24 h ban), Nginx HTTP-auth and bot-search jails |
| Automatic security patches | `unattended-upgrades` applies OS security updates nightly |
| HTTPS flags off by default | `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` all default `False` — login works on HTTP-only until SSL is confirmed |
| Secrets in `.env` | `SECRET_KEY` and all sensitive flags are never committed to git |
| LF line endings | `.gitattributes` enforces LF for all shell scripts — no `bad interpreter` errors on Ubuntu |
