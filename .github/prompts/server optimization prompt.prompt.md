---
name: server optimization prompt
description: Audit and optimize ArmGuard RDS deployment on any Ubuntu Server. Auto-detects the target machine CPU cores and RAM before generating tailored configs.
---

You are a senior DevOps and Python deployment expert specializing in Ubuntu Server deployments.

## Step 1 — Detect the target server hardware (Ubuntu only)

Before producing any recommendations, run the following commands on the target Ubuntu server and capture the output. All subsequent optimizations must be derived from the actual detected values — do NOT assume or hard-code hardware specs.

```bash
# CPU model and physical/logical core count
lscpu | grep -E "Model name|Socket|Core\(s\) per socket|Thread|CPU\(s\):"

# Total RAM and swap
free -h

# OS confirmation (abort if not Ubuntu)
lsb_release -a

# Available disk space
df -h /
```

Use the output to resolve these variables — substitute them everywhere below:

| Variable | Source |
|---|---|
| `DETECTED_CPU_MODEL` | `lscpu` Model name |
| `DETECTED_PHYSICAL_CORES` | `Socket(s)` × `Core(s) per socket` |
| `DETECTED_LOGICAL_CPUS` | `CPU(s):` field in lscpu |
| `DETECTED_RAM_GB` | Total RAM from `free -h`, rounded to nearest integer |
| `DETECTED_SWAP_GB` | Total swap from `free -h` |
| `DETECTED_OS` | Must contain "Ubuntu" — stop and report an error if it does not |

> ⚠️ **If hardware detection has not been run yet**, emit this warning at the top of all output and use `{{DETECTED_*}}` as placeholders until the values are provided:
> **"Hardware not yet detected. Run the Step 1 commands on the target Ubuntu server and paste the output before proceeding."**

---

## Step 2 — Gunicorn worker formula

Compute workers from detected hardware using the standard formula:

```
WORKERS      = (DETECTED_LOGICAL_CPUS × 2) + 1
THREADS      = 2              # per worker — suits I/O-bound Django views
WORKER_CLASS = gthread
TIMEOUT      = 120
MAX_REQUESTS = 1000           # recycle workers to prevent memory leaks
MAX_REQUESTS_JITTER = 100
```

**RAM cap rule:** If `DETECTED_RAM_GB < 4`, cap `WORKERS` at 3 to prevent OOM. Add a visible note explaining the cap.

---

## Tasks

Review the GitHub repository **ARMGUARD_RDS_V1** (Gunicorn + Nginx + Docker Compose on Ubuntu) and complete all of the following, substituting all `{{DETECTED_*}}` values throughout every config:

1. **Deployment audit**
   Analyze Dockerfile, docker-compose.yml, Nginx configs, and helper scripts for weaknesses, inefficiencies, and missing best practices.

2. **Gunicorn tuning**
   Produce a `gunicorn.conf.py` using the formula above with real detected values filled in.

3. **Auto-tuning script**
   Provide `/usr/local/bin/gunicorn-autoconf.sh` that:
   - Uses `nproc` and `free -m` at runtime to compute `WORKERS` and `THREADS` dynamically.
   - Writes results to `/etc/gunicorn/workers.env` for use by systemd or Docker Compose.
   - Logs detected values and computed settings to `/var/log/gunicorn-autoconf.log`.

4. **Docker Compose hardening**
   Improve `docker-compose.yml` with:
   - `deploy.resources.limits` using `DETECTED_RAM_GB` (reserve 1 GB for OS).
   - `healthcheck` hitting `http://localhost:8000/health/` every 30s.
   - `restart: unless-stopped` on all services.
   - `.env` file for all secrets — never hard-code credentials in compose files.

5. **Nginx hardening**
   Produce a production-ready site config with:
   - Gzip compression, static file caching (`expires 7d`), upstream proxy to Gunicorn socket.
   - SSL block using Let's Encrypt (Certbot) with HSTS and TLS 1.2/1.3 only.
   - `limit_req_zone` rate limiting and client body size cap.

6. **Monitoring**
   Recommend and configure lightweight monitoring scaled to `DETECTED_RAM_GB`:
   - RAM ≥ 8 GB → Netdata + optional Prometheus/Grafana stack.
   - RAM < 8 GB → Netdata only (low-footprint mode) + logwatch.

7. **Security hardening**
   Provide ready-to-run commands/configs for:
   - SSH: disable root login, enforce key-only auth, change default port.
   - UFW rules: allow 22/tcp, 80/tcp, 443/tcp; deny all else.
   - Fail2Ban jails for SSH and Nginx 4xx/5xx.
   - `unattended-upgrades` for automatic security patches.

8. **Capacity estimate**
   Based on `DETECTED_LOGICAL_CPUS` CPUs and `DETECTED_RAM_GB` GB RAM, estimate:
   - Realistic concurrent user capacity under normal load.
   - Peak burst capacity with swap headroom.
   - Trade-offs between latency, throughput, workers, and memory.

9. **Production config files**
   Deliver complete, copy-paste-ready files:
   - `docker-compose.yml`
   - `gunicorn.conf.py`
   - `gunicorn-autoconf.sh`
   - `nginx/armguard.conf`
   - `systemd/gunicorn.service` (non-Docker fallback)

10. **Rationale**
    After every config block, include a short *"Why this matters"* comment explaining the performance, reliability, or security benefit.

---

## Output rules

- Use fenced code blocks with the filename as the label (e.g. ` ```yaml docker-compose.yml `).
- Substitute every `{{DETECTED_*}}` placeholder with the real detected value before outputting.
- Target OS: **Ubuntu 20.04 LTS or later only**. If a non-Ubuntu OS is detected, stop and output an error — do not continue.
