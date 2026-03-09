# ARMGUARD_RDS_V1 — Deployment & Security Gaps Analysis

**Target Platform:** HP ProDesk Mini Computer  
**Target OS:** Latest Ubuntu Server (24.04 LTS)  
**Analysis Date:** 2026-03-09  
**Last Updated:** 2026-03-09 (Session 12 — full diagnostic review; 2 critical runtime bugs fixed: `_get_client_ip` missing from `users/models.py`; `acquired_date` invalid field in `api/serializers.py`. All gaps remain resolved.)  
**Compared Version:** ARMGUARD_RDS_v.2 (Enterprise)

---

## Executive Summary

This document tracks the gap analysis between **ARMGUARD_RDS_V1** and **ARMGUARD_RDS_v.2** regarding deployment readiness and security for production deployment on an HP ProDesk Mini running Ubuntu Server 24.04 LTS.

**Updated Finding (Session 10):** V1 is now fully production-hardened. All high-priority and medium-priority security gaps have been resolved through sessions 1–10. V1 now implements TOTP-based MFA, single-session enforcement, comprehensive security headers (CSP, HSTS, X-Frame-Options, Referrer-Policy, **Permissions-Policy**), audit logging with **user-agent capture** and **SHA-256 integrity hashes**, **DeletedRecord** soft-delete model, **DRF API throttle classes**, **SHA-256 backup checksums**, **optional GPG-encrypted backups**, and **filename sanitization** on file uploads. Deployment scripts are complete and tested.

**Remaining work (optional/N/A for V1):** password history, Django Axes brute-force lockout, device fingerprinting, PostgreSQL migration, Redis/WebSocket layer — all marked Low/N/A as the LAN-only use case does not require them.

---

## Table of Contents

1. [Deployment Readiness Gap Analysis](#1-deployment-readiness-gap-analysis)
2. [Security Gap Analysis](#2-security-gap-analysis)
3. [HP ProDesk Mini Compatibility Notes](#3-hp-prodesk-mini-compatibility-notes)
4. [Ubuntu Server 24.04 LTS Specific Requirements](#4-ubuntu-server-2404-lts-specific-requirements)
5. [Recommendations & Action Plan](#5-recommendations--action-plan)
6. [Quick Reference Checklist](#6-quick-reference-checklist)

---

## 1. Deployment Readiness Gap Analysis

### 1.1 Automated Deployment Scripts

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Automated deployment script** | ✅ `scripts/deploy.sh` | ✅ `deploy`, `deploy.bat` | 🟢 Resolved |
| **Interactive deployment modes** | ✅ `--quick`, `--production`, `--domain`, `--lan-ip` | ✅ Multiple modes | 🟢 Resolved |
| **Server update script** | ✅ `scripts/update-server.sh` | ✅ `update-server.sh` | 🟢 Resolved |
| **Remote deployment helper** | ❌ Not implemented | ✅ `remote-deployment-helper.sh` | 🟡 Low (LAN-only use case) |

**V1 `scripts/deploy.sh` covers:** system packages, `armguard` system user, venv + pip install, `.env` generation, migrations + collectstatic, systemd service install, Nginx config, UFW firewall, log rotation, backup cron.

### 1.2 Systemd Service Configuration

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Django application service** | ✅ `scripts/armguard-gunicorn.service` | ✅ `armguard.service` | 🟢 Resolved |
| **Hardened service unit** | ✅ `PrivateTmp`, `NoNewPrivileges`, `ProtectSystem=strict` | ✅ Basic | 🟢 Resolved |
| **Graceful reload (HUP)** | ✅ `ExecReload=/bin/kill -s HUP $MAINPID` | ✅ Supported | 🟢 Resolved |
| **WebSocket service (Daphne)** | ❌ Not required (polling-based real-time) | ✅ `armguard-websocket.service` | 🟡 N/A for V1 |

**V1 systemd unit:** `scripts/armguard-gunicorn.service` — uses `armguard` user, `armguard.wsgi:application`, 2 workers, `EnvironmentFile`, `ProtectSystem=strict`.

### 1.3 Nginx Configuration

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Nginx configuration template** | ✅ `scripts/nginx-armguard.conf` | ✅ Full `sites-available/armguard` | 🟢 Resolved |
| **SSL/TLS block (Let's Encrypt)** | ✅ Commented-out HTTPS block + certbot instructions | ✅ Full SSL config | 🟢 Resolved |
| **Static/media file serving** | ✅ `/static/` and `/media/` alias blocks | ✅ Optimized alias | 🟢 Resolved |
| **Login rate limiting** | ✅ `limit_req_zone` 5r/m on `/accounts/login/` | ✅ Nginx rate limit | 🟢 Resolved |
| **Script execution block on media** | ✅ Blocks `.php,.py,.sh` in `/media/` | ✅ Present | 🟢 Resolved |
| **WebSocket proxy** | ❌ Not required (V1 uses HTTP polling) | ✅ WebSocket upgrade | 🟡 N/A for V1 |
| **Security headers via Nginx** | ⚠️ Django middleware handles CSP/HSTS | ✅ Redundant at Nginx | 🟡 Low (Django covers it) |

### 1.4 Database Setup

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Database backup script** | ✅ `manage.py db_backup` + `scripts/db-backup-cron.sh` | ✅ Encrypted GPG backup | 🟢 Resolved |
| **Backup automation (cron)** | ✅ Cron job installed by `deploy.sh` (daily 02:00) | ✅ Automated | 🟢 Resolved |
| **Hot-copy safe backup** | ✅ `sqlite3.Connection.backup()` (consistent snapshot) | ✅ pg_dump | 🟢 Resolved |
| **Backup rotation** | ✅ `--keep N` in `db_backup` (default 14 days) | ✅ Automated | 🟢 Resolved |
| **Encrypted backups** | ✅ Optional GPG via `ARMGUARD_BACKUP_GPG_RECIPIENT` env var | ✅ GPG-encrypted backups | 🟢 Resolved |
| **Backup integrity verification** | ✅ SHA-256 `.sha256` sidecar written beside every backup | ✅ SHA-256 checksums | 🟢 Resolved |

### 1.5 Redis/Caching

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Redis installation** | ❌ Not required for V1 | ✅ `install-redis-websocket.sh` | 🟡 N/A (V1 uses polling, not channels) |
| **Redis cache backend** | ❌ Not configured | ✅ Configured | 🟡 Optional — V1 uses Django session cache |
| **Real-time updates** | ✅ HTTP polling `/api/v1/last-modified/` | ✅ WebSockets (Redis-backed) | 🟡 V1 design choice |

### 1.6 Environment Configuration

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Production .env auto-generation** | ✅ `deploy.sh` generates with random `SECRET_KEY` | ✅ Comprehensive | 🟢 Resolved |
| **Environment validation** | ✅ `production.py` raises `ValueError` if `ALLOWED_HOSTS` empty | ✅ `check --deploy` guidance | 🟢 Resolved |
| **Secret key generation** | ✅ `deploy.sh` generates 64-char cryptographically random key | ✅ Documented | 🟢 Resolved |
| **Custom admin URL** | ✅ `DJANGO_ADMIN_URL` env var | ✅ Present | 🟢 Resolved |

**V1 production `.env` template (auto-generated by `deploy.sh`):**
```bash
DJANGO_SECRET_KEY=<64-char-random-auto-generated>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=domain.com,192.168.1.100
DJANGO_ADMIN_URL=secure-admin-<random-hex>
CSRF_TRUSTED_ORIGINS=https://domain.com,http://192.168.1.100
SECURE_HSTS_SECONDS=31536000
SECURE_SSL_REDIRECT=False   # Set True after SSL cert is installed
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

**V2 also includes (not needed for V1 SQLite):**
```bash
# Django Core Settings - CHANGE THESE
DJANGO_SECRET_KEY=your-production-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com,your-server-ip,192.168.1.100

# Database Configuration
DB_ENGINE=django.db.backends.postgresql
DB_NAME=armguard
DB_USER=armguard_user
DB_PASSWORD=your-secure-database-password
DB_HOST=localhost
DB_PORT=5432
DB_SSL_MODE=prefer

# Redis Configuration
REDIS_URL=redis://127.0.0.1:6379/1
REDIS_MAX_CONNECTIONS=50

# Security Settings
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://your-server-ip

# Django Axes (Failed Login Protection)
AXES_ENABLED=True
AXES_FAILURE_LIMIT=5
AXES_COOLOFF_TIME=1
```

---

## 2. Security Gap Analysis

### 2.1 Authentication & Authorization

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Login rate limiting** | ✅ `_RateLimitedLoginView` — 10 POST/min per IP; returns 429 | ✅ `django-ratelimit` 5/min | 🟢 Resolved |
| **Nginx login rate limit** | ✅ 5r/m in `nginx-armguard.conf` | ✅ Present | 🟢 Resolved |
| **MFA / TOTP** | ✅ `django-otp` + `OTPRequiredMiddleware` (TOTP enforced for all users) | ✅ TOTP | 🟢 Resolved |
| **Single session enforcement** | ✅ `SingleSessionMiddleware` — mismatched session → force logout | ✅ `SingleSessionMiddleware` | 🟢 Resolved |
| **Session timeout** | ✅ 8 hours (`SESSION_COOKIE_AGE=28800`) | ✅ 1 hour configurable | 🟢 Resolved |
| **Password minimum length** | ✅ 12 characters (custom validator) | ✅ Military-grade | 🟢 Resolved |
| **Password history** | ✅ `PasswordHistoryValidator` (last 5) **(S11)** | ✅ Prevents reuse | 🟢 Resolved |
| **Brute-force lockout (Django Axes)** | ✅ `_RateLimitedLoginView` 10/min + Nginx 5/min covers the need | ✅ Full integration | 🟢 Resolved (different approach) |

### 2.2 Network Security

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Firewall (UFW)** | ✅ `scripts/setup-firewall.sh` (22, 80, 443 allowed; 8000 denied) | ✅ iptables rules | 🟢 Resolved |
| **Fail2Ban** | ⚠️ Optional — SSH brute-force mitigated by UFW + login rate limiting; install via `sudo apt install fail2ban` post-deploy | ✅ `armguard.conf` | 🟡 Optional (recommended) |
| **LAN/WAN access separation** | 🔵 N/A — V1 is LAN-only by design | ✅ Dual-port 8443/443 | 🔵 N/A for V1 |
| **Network-based middleware** | 🔵 N/A — LAN deployment, single-network | ✅ `NetworkBasedAccessMiddleware` | 🔵 N/A for V1 |
| **VPN integration** | 🔵 N/A — LAN-only, no WAN exposure | ✅ WireGuard support | 🔵 N/A for V1 |

### 2.3 Device & Endpoint Security

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Admin URL customization** | ✅ `DJANGO_ADMIN_URL` env var in `settings/base.py` | ✅ Present | 🟢 Resolved |
| **Device fingerprinting/whitelist** | 🔵 N/A — single LAN workstation (not a multi-device open network) | ✅ SHA-256 hashed fingerprints | 🔵 N/A for V1 LAN use case |
| **robots.txt** | ✅ Served via Django view | ✅ Present | 🟢 Resolved |
| **security.txt** | ✅ Served via Django view | ✅ Present | 🟢 Resolved |

### 2.4 Web Application Security Headers

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Content Security Policy (CSP)** | ✅ `SecurityHeadersMiddleware` — `default-src 'self'`, `script-src 'self' 'unsafe-inline'`, `frame-ancestors 'none'` | ✅ Full CSP | 🟢 Resolved |
| **X-Frame-Options** | ✅ `X_FRAME_OPTIONS='DENY'` in settings + `SecurityHeadersMiddleware` | ✅ `DENY` | 🟢 Resolved |
| **X-Content-Type-Options** | ✅ `SECURE_CONTENT_TYPE_NOSNIFF=True` | ✅ `nosniff` | 🟢 Resolved |
| **X-XSS-Protection** | ✅ `SECURE_BROWSER_XSS_FILTER=True` | ✅ Enhanced | 🟢 Resolved |
| **Strict-Transport-Security (HSTS)** | ✅ `production.py`: 31536000s + subdomains + preload | ✅ 1-year preload | 🟢 Resolved |
| **Referrer-Policy** | ✅ `SECURE_REFERRER_POLICY='same-origin'` + `SecurityHeadersMiddleware` | ✅ `same-origin` | 🟢 Resolved |
| **Permissions-Policy** | ✅ `SecurityHeadersMiddleware` blocks geolocation, camera, mic, payment, usb, accelerometer, gyroscope | ✅ Geolocation/camera/mic blocked | 🟢 Resolved |

### 2.5 Audit & Logging

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **AuditLog model** | ✅ `AuditLog` model with `action`, `ip_address`, `user`, `timestamp` | ✅ Full model | 🟢 Resolved |
| **Login/logout tracking** | ✅ Django signals (`user_logged_in`, `user_logged_out`, `user_login_failed`) | ✅ Full action types | 🟢 Resolved |
| **IP address logging** | ✅ `AuditLog.ip_address` captured from request | ✅ Complete network context | 🟢 Resolved |
| **Application log rotation** | ✅ Rotating file handler (5MB × 5 files) at `logs/armguard.log` | ✅ Present | 🟢 Resolved |
| **OS-level log rotation** | ✅ `/etc/logrotate.d/armguard` installed by `deploy.sh` | ✅ Present | 🟢 Resolved |
| **Export management command** | ✅ `manage.py export_audit_log --days --action --user --output` | ✅ Present | 🟢 Resolved |
| **Audit log integrity (hash)** | ✅ SHA-256 of (timestamp+user+action+message) auto-computed on `AuditLog.save()`, verified via `verify_integrity()` | ✅ SHA-256 hash verification | 🟢 Resolved |
| **Deleted record preservation** | ✅ `DeletedRecord` model — captures JSON snapshot before permanent deletion | ✅ `DeletedRecord` model | 🟢 Resolved |
| **User-agent tracking** | ✅ `AuditLog.user_agent` captured from `HTTP_USER_AGENT` on login/logout | ✅ Full UA capture | 🟢 Resolved |

### 2.6 Data Protection

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **Database backups** | ✅ `manage.py db_backup` (hot-copy, rotation, secure delete) | ✅ GPG-encrypted | 🟢 Resolved |
| **Encrypted backups** | ✅ Optional GPG via `ARMGUARD_BACKUP_GPG_RECIPIENT` in `db-backup-cron.sh` **(S10)** | ✅ GPG-encrypted backups | 🟢 Resolved |
| **PostgreSQL migration** | 🔵 N/A — SQLite adequate for single-site LAN use | ✅ PostgreSQL | 🔵 N/A for V1 |
| **Database optimization config** | 🔵 N/A — SQLite auto-tunes; no config file needed | ✅ Tuned `postgresql.conf` | 🔵 N/A for V1 |
| **Database field encryption** | 🔵 N/A — LAN-only; full-disk encryption at OS level is sufficient | ✅ `EncryptedTextField` | 🔵 N/A for V1 |
| **File encryption at rest** | 🔵 N/A — media files on LAN server; OS-level disk encryption covers this | ✅ `SecureFileHandler` | 🔵 N/A for V1 |
| **Secure backup deletion** | ✅ `_secure_delete()` overwrites with zeros before unlink **(S11)** | ✅ `shred` overwrite | 🟢 Resolved |
| **SESSION_COOKIE_HTTPONLY** | ✅ `True` (JS cannot read session cookie) | ✅ Present | 🟢 Resolved |
| **CSRF_COOKIE_HTTPONLY** | ✅ `True` | ✅ Present | 🟢 Resolved |

### 2.7 API Security

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **REST API** | ✅ DRF at `/api/v1/` — token + session auth, `IsAuthenticated` default | ✅ DRF | 🟢 Resolved |
| **API authentication** | ✅ `SessionAuthentication` + `TokenAuthentication` | ✅ Token + Session | 🟢 Resolved |
| **API default permission** | ✅ `IsAuthenticated` (no anonymous access) | ✅ `IsAuthenticated` | 🟢 Resolved |
| **API pagination** | ✅ `PAGE_SIZE=50` (prevents large dumps) | ✅ Present | 🟢 Resolved |
| **API rate limiting (DRF throttle)** | ✅ `AnonRateThrottle` 10/min, `UserRateThrottle` 30/min in `REST_FRAMEWORK` | ✅ 30 requests/minute | 🟢 Resolved |
| **API input validation** | ✅ DRF serializer validation | ✅ Enhanced | 🟢 Resolved |

### 2.8 Real-Time Updates

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|-------------- |
| **Real-time staleness detection** | ✅ HTTP polling `/api/v1/last-modified/` (authenticated) | ✅ WebSockets (Redis-backed) | 🟢 Resolved (different approach) |
| **WebSocket support** | 🔵 N/A — design choice; HTTP polling at `/api/v1/last-modified/` achieves live updates for LAN latency | ✅ Daphne + channels | 🔵 N/A — V1 polling is reliable for LAN |

### 2.9 File Upload Security

| Feature | V1 Status | v2 Status | Gap Severity |
|---------|-----------|-----------|--------------|
| **File size limits** | ✅ Configured (`DATA_UPLOAD_MAX_MEMORY_SIZE`) | ✅ Configured | 🟢 Complete |
| **Media file script execution blocked** | ✅ Nginx blocks `.php,.py,.sh` in `/media/` | ✅ Present | 🟢 Resolved |
| **MIME type validation** | ✅ PDFs: magic bytes (`%PDF`) verified; Images: Pillow validates image content via `ImageField` | ⚠️ Still needs improvement | 🟢 Resolved |
| **Filename sanitization** | ✅ `_sanitize_par_upload` normalizes to ASCII and strips non-alphanumeric chars; personnel images renamed to canonical `IMG_<name>_<id>.jpeg` | ❌ None | 🟢 Resolved |
| **Antivirus scanning** | 🔵 N/A — not implemented in V2 either; out-of-scope for application layer | ❌ Not implemented in V2 either | 🔵 N/A (out-of-scope for both) |

---

## 3. HP ProDesk Mini Compatibility Notes

### 3.1 Hardware Specifications

The HP ProDesk 400 G7 Mini (or similar models) typically has:
- **CPU:** Intel Core i5/i7 (10th gen) or AMD Ryzen 5
- **RAM:** 8GB-64GB DDR4 (SO-DIMM)
- **Storage:** M.2 NVMe SSD slot + 2.5" SATA bay
- **Network:** Gigabit Ethernet (Intel I219-V)
- **Form Factor:** 1.7L mini PC

### 3.2 Recommended Configuration for ARMGUARD

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | Intel i5-10500 | Intel i7-10700 |
| **RAM** | 8GB | 16GB |
| **Storage** | 256GB NVMe | 512GB NVMe |
| **Network** | Gigabit | Gigabit (or WiFi 6) |

### 3.3 V2 Optimizations for Mini PCs

V2 includes specific optimizations for small-form-factor systems:

```bash
# From installation.md - RPi-like optimizations applied to small PCs
# PostgreSQL tuned for limited resources
max_connections = 50
shared_buffers = 128MB
effective_cache_size = 512MB
work_mem = 2MB

# Redis memory limits
maxmemory 256mb
maxmemory-policy allkeys-lru

# Session timeout reduced for security
SESSION_COOKIE_AGE=1800
```

---

## 4. Ubuntu Server 24.04 LTS Specific Requirements

### 4.1 Python Version

Ubuntu 24.04 ships with Python 3.12.x. V1 supports Python 3.12+, V2 also supports Python 3.11+.

```bash
# Verify Python version
python3 --version
# Output: Python 3.12.x
```

### 4.2 Required System Packages

**V1 requires manual installation:**
```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev python3-pip
sudo apt install -y postgresql postgresql-contrib libpq-dev
sudo apt install -y redis-server
sudo apt install -y nginx
sudo apt install -y libjpeg-dev zlib1g-dev libtiff-dev libfreetype6-dev liblcms2-dev libwebp-dev
```

**V2 provides automated installation via deployment scripts.**

### 4.3 PostgreSQL Version

Ubuntu 24.04 includes PostgreSQL 16 by default.

```bash
# Check PostgreSQL version
psql --version
# Output: psql (PostgreSQL) 16.x
```

### 4.4 Systemd Availability

Ubuntu 24.04 uses systemd by default - fully compatible with V2's service files.

### 4.5 Firewall (UFW)

Ubuntu 24.04 uses UFW by default. V2's iptables rules can be adapted:

```bash
# Recommended UFW rules for ARMGUARD
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8443/tcp  # LAN-only admin (optional)
sudo ufw enable
```

---

## 5. Recommendations & Action Plan

### 5.1 Immediate Actions (Before Production)

| Priority | Action | Status |
|----------|--------|--------|
| ✅ Done | Run `scripts/deploy.sh` to set up server | Scripted |
| ✅ Done | `DJANGO_SECRET_KEY` auto-generated by `deploy.sh` | Resolved |
| ✅ Done | `DJANGO_DEBUG=False` enforced in `production.py` | Resolved |
| ✅ Done | `ALLOWED_HOSTS` validated in `production.py` | Resolved |
| ✅ Done | systemd service (`armguard-gunicorn.service`) | Scripted |
| ✅ Done | Nginx reverse proxy (`nginx-armguard.conf`) | Scripted |
| 🟠 Next | Obtain SSL certificate (`certbot --nginx -d DOMAIN`) | After DNS setup |
| 🟠 Next | Set `SECURE_SSL_REDIRECT=True` in `.env` after SSL | After cert install |
| 🟠 Next | Create superuser account | After deploy |

### 5.2 Short-Term Actions (Within 1 Week)

| Priority | Action | Status |
|----------|--------|--------|
| ✅ Done | Login rate limiting (view-level 10/min + Nginx 5/min) | Resolved |
| ✅ Done | Automated database backups via cron | Scripted |
| ✅ Done | Log rotation (`logrotate.d/armguard`) | Scripted |
| ✅ Done | UFW firewall (`scripts/setup-firewall.sh`) | Scripted |
| 🟠 High | Implement DRF API throttle classes | ✅ Done — `AnonRateThrottle` 10/min, `UserRateThrottle` 30/min |
| 🟠 High | Add encrypted backup (GPG wraps the `.sqlite3` backup) | ✅ Done — `ARMGUARD_BACKUP_GPG_RECIPIENT` env option in `db-backup-cron.sh` |
| 🟡 Medium | Install Fail2Ban for SSH brute-force protection | Optional |

### 5.3 Medium-Term Actions (Within 1 Month)

| Priority | Action | Status |
|----------|--------|--------|
| ✅ Done | CSP headers (`SecurityHeadersMiddleware`) | Resolved |
| ✅ Done | HSTS configuration (`production.py`) | Resolved |
| ✅ Done | TOTP MFA enforcement (`OTPRequiredMiddleware`) | Resolved |
| 🟠 High | Device fingerprinting/whitelist | Remaining gap — optional for LAN-only V1 |
| 🟠 High | Audit log SHA-256 integrity verification | ✅ Done — `AuditLog.integrity_hash` auto-computed on save |
| 🟡 Medium | Add `Permissions-Policy` header to `SecurityHeadersMiddleware` | ✅ Done — all sensor/hardware APIs blocked |
| 🟡 Medium | Password history (prevent reuse) | Optional for V1 |
| 🟡 Medium | Add `gunicorn` and `psycopg2-binary` to `requirements.txt` | ✅ Done — `gunicorn==22.0.0` added |

### 5.4 Recommended V1 Dependencies to Add

Add these to `requirements.txt` before deployment:

```bash
# Production server
gunicorn==22.0.0           # WSGI server (installed by deploy.sh even if missing)

# Monitoring (optional)
psutil                     # For health check endpoints
```

Not needed for V1 (LAN, SQLite):
- `psycopg2-binary` — only if migrating to PostgreSQL
- `redis`, `django-redis` — only if adding WebSocket/cache layer
- `django-axes` — rate limiting already covers this
- `django-csp` — `SecurityHeadersMiddleware` already handles CSP

---

## 6. Quick Reference Checklist

### Pre-Deployment Checklist

- [ ] Ubuntu Server 24.04 LTS installed
- [ ] Run `sudo bash scripts/deploy.sh --domain YOUR_DOMAIN --lan-ip YOUR_IP`
- [ ] Review generated `.env` at `/var/www/armguard-v1/.env`
- [ ] Create superuser: `sudo -u armguard /var/www/armguard-v1/venv/bin/python /var/www/armguard-v1/project/manage.py createsuperuser`
- [ ] Obtain SSL certificate: `sudo certbot --nginx -d YOUR_DOMAIN`
- [ ] Update `.env`: `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- [ ] Verify service: `sudo systemctl status armguard-gunicorn`
- [ ] Verify Nginx: `sudo nginx -t && sudo systemctl status nginx`
- [ ] Run Django check: `sudo -u armguard /var/www/armguard-v1/venv/bin/python /var/www/armguard-v1/project/manage.py check --deploy`

### Security Checklist

- [ ] `DJANGO_SECRET_KEY` auto-generated (64-char random)
- [ ] `DJANGO_DEBUG=False` enforced in `production.py`
- [ ] `ALLOWED_HOSTS` set and validated in `production.py`
- [ ] `SECURE_SSL_REDIRECT=True` (after SSL cert installed)
- [ ] `SESSION_COOKIE_SECURE=True`
- [ ] `CSRF_COOKIE_SECURE=True`
- [ ] `SECURE_HSTS_SECONDS=31536000` ✅ (already in production.py)
- [ ] `DJANGO_ADMIN_URL` set to non-guessable path
- [ ] TOTP MFA enabled (`OTPRequiredMiddleware` active) ✅
- [ ] Login rate limiting active (view-level + Nginx) ✅
- [ ] UFW firewall enabled (`scripts/setup-firewall.sh`) ✅
- [ ] Daily backup cron job running ✅
- [ ] `SecurityHeadersMiddleware` active (CSP, HSTS, X-Frame, Referrer) ✅
- [ ] Audit log being written to `logs/armguard.log` ✅

### Deployment Verification Checklist

- [ ] `sudo systemctl is-active armguard-gunicorn` → `active`
- [ ] `sudo systemctl is-active nginx` → `active`
- [ ] Nginx serves static files (check `/static/admin/css/base.css`)
- [ ] Login page loads and TOTP is required
- [ ] HTTPS works with valid certificate (after certbot)
- [ ] Database backup runs: `sudo bash scripts/db-backup-cron.sh`
- [ ] Logs rotating: `ls -la /var/log/armguard/`
- [ ] `sudo -u armguard .../python manage.py check --deploy` → 0 issues
- [ ] UFW status: `sudo ufw status verbose`

---

## Appendix A: V1 → V2 Feature Migration Guide

If migrating from V1 to V2, the following components must be transferred:

### 1. Data Migration
```bash
# Export V1 SQLite data
cd ARMGUARD_RDS_V1/project
python manage.py dumpdata --format=yaml > ../data_backup.yaml

# Import to V2 (after PostgreSQL setup)
cd ARMGUARD_RDS_v.2/armguard
python manage.py loaddata ../data_backup.yaml
```

### 2. Custom Code
- Transfer any custom views from `ARMGUARD_RDS_V1/project/armguard/apps/`
- Transfer custom templates from `ARMGUARD_RDS_V1/project/armguard/templates/`
- Transfer custom static files from `ARMGUARD_RDS_V1/project/armguard/static/`

### 3. Configuration
- Recreate user accounts and permissions in V2
- Configure any custom settings in V2's `core/settings.py`

---

## Appendix B: Comparison Summary

| Category | V1 Status | v2 Status | Recommendation |
|----------|-----------|-----------|----------------|
| **Deployment Automation** | ✅ `scripts/deploy.sh` + supporting scripts | ✅ Automated | V1 now fully scripted |
| **Production Django Settings** | ✅ `settings/production.py` (SSL, HSTS, secure cookies) | ✅ Production-ready | 🟢 Resolved |
| **MFA Security** | ✅ TOTP enforced via `OTPRequiredMiddleware` | ✅ TOTP | 🟢 Resolved |
| **Security Headers** | ✅ CSP, HSTS, X-Frame-Options, Referrer-Policy, nosniff | ✅ Enterprise | 🟢 Resolved |
| **Audit Logging** | ✅ `AuditLog` model + signals + export command | ✅ Enterprise+ | 🟢 Resolved |
| **LAN/WAN Separation** | ❌ LAN-only design (not intended for WAN) | ✅ Dual-network | 🟡 N/A for V1 |
| **Encrypted Backups** | ❌ Plaintext SQLite backups | ✅ GPG-encrypted | 🟠 Remaining gap |
| **HP ProDesk Compatibility** | ✅ Compatible (x86_64, 2 Gunicorn workers) | ✅ Optimized | 🟢 Working |

---

**Document Version:** 2.0  
**Last Updated:** 2026-06-10 (Session 9)  
**Target Audience:** System Administrators, DevOps Engineers  

---

*For V1 deployment scripts, see `ARMGUARD_RDS_V1/scripts/README.md`*  
*For V2 deployment scripts, see `ARMGUARD_RDS_v.2/deploy`*  
*For V2 security documentation, see `ARMGUARD_RDS_v.2/docs/security.md`*  
*For V2 installation guide, see `ARMGUARD_RDS_v.2/docs/installation.md`*

