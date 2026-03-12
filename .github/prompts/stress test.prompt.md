---
name: stress test
description: Generate hardware-aware, authentication-aware stress test scripts for ArmGuard RDS (Gunicorn + Nginx on Ubuntu). Auto-detects server specs, holds authenticated sessions, monitors resources during tests, and produces a maximum stable concurrency report.
applyTo: "scripts/**,deploy/**,docker-compose*.yml"
---

You are a senior DevOps and performance testing expert specializing in Django + Gunicorn deployments on Ubuntu Server.

---

## ⚠️ Safety warnings — read before running

> 1. **Do NOT run these scripts on a server with live users** without scheduling a maintenance window first.
> 2. **Run the load generator from a SEPARATE machine**, not the server being tested. Running `ab`/`wrk`/`locust` on the same host as Gunicorn causes the load tool to compete for CPU, artificially inflating latency and deflating RPS — the results will be misleading.
> 3. The scripts include a `--dry-run` flag and a confirmation prompt before any load is applied.

---

## Step 1 — Detect environment before generating any scripts

Run the following **on the Ubuntu server being tested** and also note the **IP of the machine that will run the tests** (the load generator). All script parameters must be derived from actual detected values — never assume or hard-code.

```bash
# === On the SERVER being tested ===

# Hardware
lscpu | grep -E "CPU\(s\):|Core\(s\) per socket|Socket"
free -h
df -h /

# OS (must be Ubuntu 20.04+)
lsb_release -a

# Current Gunicorn config
cat /etc/gunicorn/workers.env 2>/dev/null || \
  ps aux | grep gunicorn | grep -v grep | head -5

# Server IP and protocol
hostname -I | awk '{print $1}'
curl -sk -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost/ | head -1

# Django DB engine (affects connection pool pressure at high concurrency)
grep -E "ENGINE|HOST|CONN_MAX_AGE" project/armguard/settings*.py 2>/dev/null | head -10

# === On the LOAD GENERATOR machine ===
# (run this separately and note the output)
hostname -I | awk '{print $1}'
which ab wrk locust k6 2>/dev/null || echo "Tools not yet installed"
```

Resolve these variables and substitute them throughout every generated script:

| Variable | Source |
|---|---|
| `DETECTED_LOGICAL_CPUS` | `CPU(s):` from lscpu |
| `DETECTED_RAM_GB` | Total RAM from `free -h`, integer |
| `DETECTED_SERVER_IP` | Server `hostname -I` |
| `DETECTED_SERVER_PROTOCOL` | `http` or `https` |
| `DETECTED_GUNICORN_WORKERS` | Current worker count from ps/workers.env |
| `DETECTED_DB_ENGINE` | `sqlite3`, `postgresql`, or `mysql` from settings |
| `DETECTED_CONN_MAX_AGE` | `CONN_MAX_AGE` value from settings (default 0 if unset) |
| `DETECTED_OS` | Must be Ubuntu 20.04+ — stop with error if not |
| `LOAD_GENERATOR_IP` | IP of the machine running the tests |

> ⚠️ **If Step 1 output has not been provided**, emit this warning block and use `{{DETECTED_*}}` placeholders:
> **"Environment not yet detected. Paste the Step 1 command output before proceeding."**

---

## Step 2 — Endpoint strategy

> **Critical:** ArmGuard RDS endpoints require an authenticated Django session. `ab` and `wrk` are stateless — without session injection they measure 302 redirects, not real Django view load. Every authenticated test MUST go through `auth_session.sh` first.

Generate tests for three endpoint tiers:

| Tier | Example URLs | Auth | Tool |
|---|---|---|---|
| **Static** | `/static/css/main.css`, `/static/js/app.js` | No | `wrk` |
| **Public** | `/accounts/login/` | No | `ab` + `wrk` |
| **Authenticated** | `/`, `/transactions/`, `/print/reprint-tr/` | Yes — session cookie | `locust` (Python) with think time |

**Why locust for authenticated tiers, not wrk/ab:**
`wrk` can inject cookies via a Lua script (see `scripts/wrk_auth.lua` deliverable below) but cannot simulate realistic think time between requests. `locust` supports `wait_time = between(1, 3)` which models real user pacing. Use `wrk` + Lua only for raw throughput ceiling tests; use `locust` for realistic concurrency modelling.

---

## Deliverable scripts

### 1. `scripts/auth_session.sh` — Session cookie helper *(run this first)*

Standalone script that:
1. Accepts `BASE_URL`, `USERNAME`, `PASSWORD` as arguments (or reads from `.env`).
2. GETs the login page and extracts `csrftoken` from the `Set-Cookie` header.
3. POSTs credentials + CSRF token and captures `sessionid` + `csrftoken` from the response cookies.
4. Writes them to `/tmp/armguard_session.env` as:
   ```bash
   export SESSION_COOKIE="sessionid=<value>"
   export CSRF_TOKEN="<value>"
   export AUTH_COOKIE_HEADER="sessionid=<value>; csrftoken=<value>"
   ```
5. Verifies that `GET /` with the session cookie returns HTTP 200 (not 302). If not, exit with error: `"Authentication failed — check USERNAME/PASSWORD"`.
6. Usage: `source <(./auth_session.sh https://{{DETECTED_SERVER_IP}} admin password123)`
   `stress_test.sh` must `source /tmp/armguard_session.env` before running any authenticated test.

### 2. `scripts/wrk_auth.lua` — Lua cookie injection script for wrk

Injects the session cookie into every wrk request for raw throughput tests:
```lua
-- Loaded via: wrk -s scripts/wrk_auth.lua ...
-- SESSION_COOKIE env var must be set (from auth_session.sh)
wrk.headers["Cookie"] = os.getenv("AUTH_COOKIE_HEADER")
wrk.headers["X-CSRFToken"] = os.getenv("CSRF_TOKEN")
```

### 3. `scripts/stress_test.sh` — Master orchestrator

Must:
- Print `--dry-run` mode showing all commands without sending load.
- Prompt: `"Load will target {{DETECTED_SERVER_IP}} FROM {{LOAD_GENERATOR_IP}}. Continue? [y/N]"`
- Refuse to run if `LOAD_GENERATOR_IP == DETECTED_SERVER_IP` (same-host guard) unless `--force-local` flag is passed with an explicit warning.
- Auto-install missing tools (`ab`, `wrk`, `locust`) via `apt-get` if running on Ubuntu; skip silently on other OS.
- Source `/tmp/armguard_session.env` (created by `auth_session.sh`) for authenticated tests.
- Snapshot the current Gunicorn worker count and Django `CONN_MAX_AGE` as baseline metadata.
- Wrap every tool invocation with `timeout 120` to prevent indefinite hangs.
- Run a **warm-up phase**: 20 requests at concurrency 1 to prime Django caches and DB connection pool.
- Wait **15 seconds cooldown** between concurrency levels to let the server return to baseline.
- Run incremental levels: **1, 10, 25, 50, 100, 200** (include 500 only if `DETECTED_RAM_GB >= 8`).
- At each level, run for **30 seconds** duration (not fixed request count).
- After each level, evaluate pass/fail thresholds (Step 3). Stop escalating on first FAIL.
- Launch `monitor_resources.sh` in background; kill it when tests complete.
- Save all tool output + resource CSV to `/var/log/armguard-stress/YYYY-MM-DD_HH-MM/` with a `metadata.json` containing all `DETECTED_*` values.
- Run `analyse_results.sh` automatically at the end.

### 4. `scripts/monitor_resources.sh` — Background resource sampler

Runs in parallel. Every 5 seconds appends to `resources.csv`:
```
timestamp,cpu_percent,ram_used_mb,swap_used_mb,load_avg_1m,gunicorn_workers_active,db_connections
```
- `cpu_percent` from `top -bn1 | grep "Cpu(s)"`
- `ram_used_mb` / `swap_used_mb` from `free -m`
- `gunicorn_workers_active` from `ps aux | grep gunicorn | grep -v grep | wc -l`
- `db_connections` from `ss -tn | grep :5432 | wc -l` (PostgreSQL) or `0` for SQLite

### 5. `scripts/locustfile.py` — Realistic authenticated load test

A `locust` user class that:
- Authenticates via the login flow on `on_start()` (calls `auth_session.sh` logic in Python using `requests`).
- Exercises: `GET /`, `GET /transactions/`, `GET /print/reprint-tr/` in rotation.
- Uses `wait_time = between(1, 3)` to simulate realistic user think time.
- Reports p50, p95, p99 latency and error rate per endpoint via locust's built-in stats.

### 6. `scripts/analyse_results.sh` — Post-test report generator

Parses result files from the output directory. Must handle all three tool output formats:
- `ab` output: parse `Requests per second`, `Time per request (mean)`, `Failed requests`.
- `wrk` output: parse `Requests/sec`, `Latency` percentiles from wrk's `--latency` flag output.
- `locust` CSV: parse `Name,# requests,# failures,Median response time,95%ile,99%ile`.

Produces a unified report:
```
=== ARMGUARD RDS STRESS TEST REPORT ===
Tested:    {{DETECTED_SERVER_IP}}  (from {{LOAD_GENERATOR_IP}})
CPU:       {{DETECTED_LOGICAL_CPUS}} cores   RAM: {{DETECTED_RAM_GB}} GB
Gunicorn:  {{DETECTED_GUNICORN_WORKERS}} workers   DB: {{DETECTED_DB_ENGINE}} (CONN_MAX_AGE={{DETECTED_CONN_MAX_AGE}})

Level       RPS     p50ms   p95ms   p99ms   Errors   Status
--------    -----   -----   -----   -----   ------   ------
1 users     42      8       23      45      0.0%     ✅ PASS
10 users    38      21      89      201     0.0%     ✅ PASS
25 users    35      55      210     480     0.1%     ⚠️  WARN
50 users    28      190     850     1800    0.8%     ✅ PASS
100 users   12      950     3200    5100    4.2%     ❌ FAIL

Maximum stable concurrency: 50 users
Bottleneck: p95 exceeded 2000ms at 100 users
Recommendation: (see Step 4)
```

### 7. `scripts/cleanup.sh` — Post-test teardown

After testing:
- Removes test Django sessions from the DB:
  - SQLite: `python manage.py clearsessions`
  - PostgreSQL: `python manage.py clearsessions`
- Removes `/tmp/armguard_session.env`.
- Prints a summary of log files saved and their sizes.

---

## Step 3 — Pass/fail thresholds

**FAIL** (stop escalating) if ANY of:
- Error rate > 1%
- p95 latency > 2000 ms
- p99 latency > 5000 ms
- Any HTTP 502 or 503 response detected
- `monitor_resources.sh` reports swap usage > 50% of `DETECTED_SWAP_GB`

**WARNING** (continue but flag) if ANY of:
- Error rate 0.1%–1%
- p95 latency 1000–2000 ms
- Load average > `DETECTED_LOGICAL_CPUS` × 1.5

---

## Step 4 — Gunicorn tuning recommendation

After analysis, compute the recommended worker count:
```
# The correct formula — based on CPU, not on max concurrency
RECOMMENDED_WORKERS = (DETECTED_LOGICAL_CPUS × 2) + 1

# If max stable concurrency was lower than expected, check connection pool first:
# If DETECTED_CONN_MAX_AGE == 0 and DETECTED_DB_ENGINE != sqlite3:
#   → Set CONN_MAX_AGE = 60 before increasing workers (connection churn is likely the bottleneck)

# RAM safety cap: each Gunicorn worker uses ~80–120 MB for a Django app
MAX_WORKERS_BY_RAM = floor((DETECTED_RAM_GB * 1024 - 1024) / 100)
FINAL_WORKERS = min(RECOMMENDED_WORKERS, MAX_WORKERS_BY_RAM)
```

Output the exact `gunicorn.conf.py` lines and the `CONN_MAX_AGE` Django setting to apply.

---

## Output rules

- All `.sh` scripts must begin with `#!/usr/bin/env bash` and `set -euo pipefail`.
- Use fenced code blocks with the filename as the label.
- Every non-obvious command must have an inline `# comment` explaining why.
- Scripts must be idempotent — safe to re-run without side effects.
- Substitute all `{{DETECTED_*}}` values before outputting.
- Target OS for the *server*: Ubuntu 20.04 LTS or later. Non-Ubuntu server → stop with error.
- The load generator can be any Linux/macOS machine; note tool installation differences.
