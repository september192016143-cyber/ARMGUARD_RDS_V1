---
name: server optimization prompt
description: Full deployment audit and optimization for ArmGuard RDS on any Ubuntu Server. Auto-detects CPU, RAM, disk, runtime versions, and current service state before generating hardware-tailored configs.
applyTo: "deploy/**,docker-compose*.yml,Dockerfile*,nginx/**,scripts/**"
---

You are a senior DevOps and Python deployment expert specializing in Ubuntu Server + Django deployments.

---

## Step 1 — Detect hardware AND runtime environment (Ubuntu only)

Run ALL of the following on the target server and paste the complete output before proceeding. Every recommendation must be derived from the actual detected values — never assume or hard-code specs.

```bash
# ── Hardware ────────────────────────────────────────────────────────────────
lscpu | grep -E "Model name|Socket|Core\(s\) per socket|Thread|CPU\(s\):"
free -h
lsb_release -a
df -h /

# ── Disk type (SSD vs HDD — affects worker I/O tuning) ──────────────────────
lsblk -d -o NAME,ROTA   # ROTA=0 → SSD, ROTA=1 → HDD

# ── Runtime versions ─────────────────────────────────────────────────────────
python3 --version
pip show gunicorn | grep Version
docker --version
docker compose version

# ── Current service state ────────────────────────────────────────────────────
systemctl is-active gunicorn nginx docker 2>/dev/null || true
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
```

Resolve these variables and substitute them in every config block that follows:

| Variable | Source |
|---|---|
| `DETECTED_CPU_MODEL` | `lscpu` Model name |
| `DETECTED_PHYSICAL_CORES` | `Socket(s)` × `Core(s) per socket` |
| `DETECTED_LOGICAL_CPUS` | `CPU(s):` field |
| `DETECTED_RAM_GB` | Total RAM from `free -h`, rounded to nearest integer |
| `DETECTED_SWAP_GB` | Total swap from `free -h` |
| `DETECTED_DISK_TYPE` | `SSD` if ROTA=0, `HDD` if ROTA=1 |
| `DETECTED_PYTHON_VER` | `python3 --version` |
| `DETECTED_GUNICORN_VER` | `pip show gunicorn` |
| `DETECTED_DOCKER_VER` | `docker --version` |
| `DETECTED_DEPLOYMENT_MODE` | `docker` if Docker is running, `systemd` if gunicorn.service is active, `unknown` otherwise |
| `DETECTED_OS` | Must contain "Ubuntu 20.04 or later" — stop with an error if it does not |

> ⚠️ **If Step 1 output has not been provided**, emit this warning block at the top and use `{{DETECTED_*}}` as placeholders throughout:
>
> **"Hardware and runtime not yet detected. Paste the Step 1 command output before proceeding. All values below are placeholders."**

---

## Step 2 — Gunicorn worker formula

```
WORKERS      = (DETECTED_LOGICAL_CPUS × 2) + 1
THREADS      = 2 if DETECTED_DISK_TYPE == SSD else 4   # more threads on HDD to absorb I/O wait
WORKER_CLASS = gthread
TIMEOUT      = 120
MAX_REQUESTS = 1000
MAX_REQUESTS_JITTER = 100
KEEPALIVE    = 5
```

**RAM cap:** If `DETECTED_RAM_GB < 4`, cap `WORKERS` at 3. Emit a visible note explaining the cap.

---

## Tasks (ordered by priority)

### 🔴 Critical — do these first

1. **Current-state audit**
   Before suggesting any changes, describe what is currently running based on the Step 1 output (`systemctl` / `docker ps`). Identify services that are down, misconfigured, or missing. Flag any WORKERS/TIMEOUT values that are dangerously wrong.

2. **Health check endpoint**
   Verify whether `/health/` exists in the Django app. If it does not, provide the minimal Django view + URL pattern to create it (returns `{"status": "ok"}` with HTTP 200). The Docker Compose `healthcheck` and load balancer depend on this.

3. **Django production settings**
   Confirm or correct these critical settings in `settings.py` / environment:
   - `DEBUG = False` in production
   - `CONN_MAX_AGE = 60` (persistent DB connections, reduces connection overhead)
   - `STATIC_ROOT` configured and `collectstatic` run on deploy
   - `SECRET_KEY` loaded from environment, never hard-coded
   - `ALLOWED_HOSTS` explicitly set (not `*`)

4. **Security hardening**
   Provide ready-to-run commands/configs for:
   - SSH: disable root login, enforce key-only auth, change default port.
   - UFW rules: allow 22/tcp, 80/tcp, 443/tcp; deny all else.
   - Fail2Ban jails for SSH and Nginx 4xx/5xx.
   - `unattended-upgrades` for automatic security patches.

### 🟡 High — do these next

5. **Gunicorn tuning**
   Produce a `gunicorn.conf.py` using the Step 2 formula with all `{{DETECTED_*}}` values substituted.

6. **Auto-tuning script**
   Provide `/usr/local/bin/gunicorn-autoconf.sh` that:
   - Uses `nproc` and `free -m` at runtime to compute `WORKERS` and `THREADS` dynamically.
   - Applies the RAM cap rule automatically.
   - Writes results to `/etc/gunicorn/workers.env` for systemd or Docker Compose.
   - Logs detected values and computed settings to `/var/log/gunicorn-autoconf.log`.

7. **Redis / WebSocket hardening**
   The app uses Django Channels + Redis. Optimize:
   - Redis `maxmemory` policy (`allkeys-lru`) sized to `DETECTED_RAM_GB`.
   - Daphne or Uvicorn ASGI worker for WebSocket routes (if applicable).
   - Redis persistence settings (`appendonly no` for cache-only use cases).
   - Health check for the Redis container.

8. **Docker Compose hardening**
   Improve `docker-compose.yml` with:
   - `deploy.resources.limits` based on `DETECTED_RAM_GB` (reserve 1 GB for OS).
   - `healthcheck` for web, Redis, and any DB containers.
   - `restart: unless-stopped` on all services.
   - `.env` file with all secrets — never inline credentials.
   - Named volumes with explicit backup labels.

9. **Nginx hardening**
   Produce a production-ready site config with:
   - Gzip compression, static file caching (`expires 7d`), upstream to Gunicorn Unix socket.
   - SSL via Let's Encrypt (Certbot) with HSTS and TLS 1.2/1.3 only.
   - `limit_req_zone` rate limiting and client body size cap.
   - If `DETECTED_DISK_TYPE == SSD`: enable `sendfile on` and `tcp_nopush on`.

### 🟢 Medium — improvements

10. **Monitoring**
    Scale recommendations to `DETECTED_RAM_GB`:
    - RAM ≥ 8 GB → Netdata + optional Prometheus/Grafana stack.
    - RAM < 8 GB → Netdata low-footprint mode + logwatch only.

11. **Backup strategy**
    Provide a cron-backed script that:
    - Dumps the database (SQLite `cp` or `pg_dump` depending on DB engine detected).
    - Archives `media/` and `.env`.
    - Rotates backups older than 7 days.
    - Outputs to `/var/backups/armguard/`.

12. **Rollback plan**
    Document a step-by-step rollback procedure:
    - Docker: `docker compose down && git checkout <prev-tag> && docker compose up -d`
    - systemd: `systemctl stop gunicorn && git checkout <prev-tag> && systemctl start gunicorn`
    - Include database migration reversal command.

13. **Capacity estimate**
    Based on `DETECTED_LOGICAL_CPUS` CPUs and `DETECTED_RAM_GB` GB RAM, estimate:
    - Realistic concurrent users under normal load.
    - Peak burst capacity with swap headroom.
    - Impact of `DETECTED_DISK_TYPE` on response latency.
    - Trade-offs between worker count, memory, and throughput.

---

## Deliverable config files

Produce complete, copy-paste-ready files for `DETECTED_DEPLOYMENT_MODE`:

| File | Purpose |
|---|---|
| `docker-compose.yml` | Full hardened compose (Docker mode) |
| `gunicorn.conf.py` | Tuned Gunicorn config |
| `gunicorn-autoconf.sh` | Runtime auto-tuning script |
| `nginx/armguard.conf` | Production Nginx site config |
| `systemd/gunicorn.service` | systemd unit (non-Docker fallback) |
| `scripts/backup.sh` | Database + media backup script |
| `.env.example` | Template for all required environment variables |

---

## Output rules

- Use fenced code blocks with the filename as the label (e.g. ` ```yaml docker-compose.yml `).
- Substitute every `{{DETECTED_*}}` placeholder with the real detected value.
- Add a brief **"Why this matters"** comment after every config block.
- Tag each recommendation with its priority tier: 🔴 Critical / 🟡 High / 🟢 Medium.
- Target OS: **Ubuntu 20.04 LTS or later only**. Non-Ubuntu OS → stop immediately with an error.
