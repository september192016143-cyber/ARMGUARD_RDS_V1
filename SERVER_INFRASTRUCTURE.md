# ARMGUARD RDS V1 — Server Infrastructure Documentation

**Date:** May 5, 2026  
**Application:** ARMGUARD RDS V1  
**Framework:** Django 6.0.3 / Python 3.12  
**Server:** Ubuntu 24.04 LTS — `192.168.0.162`  
**Deployment:** Gunicorn 22.0.0 + Nginx (SSL)  
**Last reviewed commit:** `0c8a270`

---

## 1. Application Summary

ARMGUARD is a military small-arms inventory and transaction management system for an Air Force armory unit. Core modules:

- **Inventory** — Pistols, Rifles, Magazines, Ammunition, Accessories
- **Personnel** — Personnel records, groupings, ID card generation
- **Transactions** — Withdrawal / Return with QR and PDF receipts
- **Dashboard** — Aggregated analytics, activity feed
- **Camera** — Mobile device pairing for serial number image capture
- **REST API** — Read-only endpoints (DRF)
- **Settings** — OREX simulation, system configuration, audit logs
- **Print** — PDF TR form filling with watermarking, item tag generation

---

## 2. Current Hardware Specifications

| Component | Specification |
|-----------|---------------|
| CPU | 12 logical cores |
| RAM | 15,852 MB (~15 GB) |
| Disk | HDD, 226 GB total |
| Disk used | 9.7 GB (206 GB free, 5% used) |
| OS | Ubuntu 24.04 LTS |
| Database | SQLite 3 (WAL mode, 6.8 MB) |
| Cache | FileBasedCache (`project/../cache/`) |
| Sessions | Django database backend |

### Gunicorn Configuration (auto-tuned)

| Parameter | Value | Formula |
|-----------|-------|---------|
| Workers | 25 | (12 × 2) + 1 = 25 |
| Threads | 4 | Disk type = HDD → THREADS=4 |
| Concurrent capacity | 100 requests | 25 × 4 |
| CONN_MAX_AGE | 600 s | Per-worker persistent connection |

### Media Breakdown

| Path | Size |
|------|------|
| `personnel_id_cards/` | 101 MB |
| `serial_capture_temp/` | 100 MB |
| `personnel_images/` | 37 MB |
| `item_id_tags/` | 32 MB |
| `TR_PDF/` | 25 MB |
| `qr_code_images_pistol/` | 13 MB |
| `qr_code_images_rifle/` | 4.3 MB |
| `qr_code_images_personnel/` | 2.5 MB |
| Others | ~10 MB |
| **Total media** | **314 MB** |

---

## 3. Architecture Overview

```
Internet
   │
   ▼
Nginx (SSL/TLS, port 443)
   │  static files served via WhiteNoise
   │  media files served via Django FileResponse
   ▼
Gunicorn (WSGI, 25 workers × 4 threads)
   │
   ├── Django 6.0.3 (synchronous — no async views, no Channels)
   │     ├── SecurityHeadersMiddleware (CSP, HSTS, X-Frame-Options)
   │     ├── SingleSessionMiddleware (1 active session per user)
   │     ├── ActivityLogMiddleware (writes 1 DB row per request)
   │     └── Apps: inventory, personnel, transactions, users, camera,
   │               dashboard, print, api
   │
   ├── SQLite 3 (WAL mode) ← file lock bottleneck
   │
   ├── FileBasedCache (1000 entries max) ← race conditions
   │
   └── Daemon threads (OREX simulation — no task queue)
```

---

## 4. Background & Heavy Processes

### 4.1 OREX Withdrawal Simulation

- **Trigger:** Superuser-only — `/users/settings/simulate-orex/` (POST)
- **Scope:** 1–500 personnel (default 114); configurable delay 0–60 s per transaction
- **Per-run operations:**
  - Load active personnel without rifle + available rifles (2 queries)
  - Create N `Transaction` objects with `full_clean()` validation
  - Create `ActivityLog` + `AuditLog` per transaction
  - Atomic progress updates to `SimulationRun` table
- **Duration:** 5–500 seconds depending on delay + personnel count
- **Thread model:** Python `daemon=True` thread, single run enforced
- **Lock impact:** Holds SQLite write lock for the full duration; blocks all user writes

### 4.2 QR Code Generation

- **Library:** qrcode 8.2 + Pillow 12.1.1
- **Output:** 600×600 px PNG, error correction=HIGH, DPI=300
- **Trigger:** Item/personnel creation, bulk generate endpoint
- **Model:** Per-item, stored as `ImageField`

### 4.3 Item Tag Generation

- **Output:** 900×450 px PNG (Pillow text overlay)
- **Execution:** Synchronous — blocks request thread until complete
- **Trigger:** Bulk endpoint, individual regenerate, print workflow

### 4.4 Personnel ID Card Generation

- **Output:** 638×1013 px front + back PNGs (overlay on template)
- **Operations:** Photo resize, text overlay (rank, AFSN, ID), QR placement
- **Execution:** Synchronous — blocks request thread
- **Storage:** 101 MB current

### 4.5 PDF Form Filling (TR Documents)

- **Library:** PyMuPDF (fitz) 1.27.1
- **Operation:** Fill `Temp_Rec.pdf` fields + diagonal watermark (45°, 3 rows per half-page)
- **Execution:** Synchronous — blocks request thread (1–3 s for large PDFs)
- **Trigger:** Every transaction PDF download

### 4.6 Activity Logging

- **Trigger:** Every HTTP request (all non-static requests)
- **Writes:** 1 `ActivityLog` row per request
- **Impact at 25 workers:** ~25 writes/second to SQLite continuously

### 4.7 Bulk Import

- **Libraries:** openpyxl 3.1.5, gspread 6.0.0, google-auth
- **Source:** .xlsx file or Google Sheets
- **Execution:** Synchronous, no progress tracking, no cancellation

---

## 5. Critical Bottlenecks

### CRITICAL — SQLite with 25 Workers

SQLite uses a file-level write lock. Only one worker can write at a time. With 25 workers all writing (activity logs, transactions, sessions), workers queue behind the lock. The `timeout=5` setting means any write that waits more than 5 seconds raises:

```
django.db.utils.OperationalError: database is locked
```

**Signal to watch for:** This error in `journalctl -u armguard-gunicorn`.

### CRITICAL — ActivityLogMiddleware

Every request creates a DB write. At 25 concurrent workers this is a constant stream of writes. Under moderate load (e.g., 20 users navigating pages), this alone can saturate the SQLite write lock.

### HIGH — FileBasedCache Race Conditions

`cache.incr()` and `cache.add()` are not atomic in `FileBasedCache`. Consequence: the API rate limiter (60 req/hour per user) can be bypassed under concurrent load. Dashboard cache invalidation may also fail silently.

### HIGH — OREX Simulation During Live Use

Running OREX while users are active causes all user writes to queue behind 500 simulation writes. Users experience slow responses or timeout errors for the full simulation duration.

### MEDIUM — Synchronous PDF/Image Generation

No task queue. PDF watermarking, ID card generation, item tags all block a Gunicorn worker thread for 1–5 seconds per operation. Under concurrent load this exhausts the thread pool.

### MEDIUM — HDD Storage

| Operation | HDD latency | NVMe SSD latency |
|-----------|-------------|------------------|
| SQLite random read | 5–15 ms | 0.1–0.5 ms |
| WAL checkpoint write | 10–30 ms | 0.5–2 ms |
| Media file write | 5–10 ms | 0.1–1 ms |
| Backup (same disk) | Competes with live I/O | Minimal impact |

---

## 6. Recommended Specifications

### Option A — Current Use (5–15 concurrent users, SQLite acceptable)

```
CPU:      4+ cores
RAM:      8 GB
Disk:     SSD (NVMe preferred), 100 GB minimum
Gunicorn: 8 workers, 2 threads  ← reduce from 25
Database: SQLite 3 (WAL) — monitor "database is locked" errors
Cache:    Redis 7+  (replace FileBasedCache)
```

**Quick-win changes (no hardware needed):**
1. Set workers to 8 in `/etc/gunicorn/workers.env` — immediate reduction in lock contention
2. Install Redis and set `CACHE_BACKEND=django.core.cache.backends.redis.RedisCache` — fixes rate-limiter

---

### Option B — Operational Use (20–50 concurrent users)

```
CPU:      8 cores (2.4+ GHz)
RAM:      16 GB
Disk:     NVMe SSD, 500 GB
Gunicorn: 16 workers, 4 threads
Database: PostgreSQL 15+  ← required at this scale
Cache:    Redis 7+ (Sentinel for HA)
Backup:   Daily incremental, stored on separate volume
```

**Why PostgreSQL:** Row-level locking eliminates write serialization. The app already supports it — set `DB_ENGINE=django.db.backends.postgresql` in `.env` and run `manage.py migrate`.

---

### Option C — Production Grade (200+ concurrent users)

```
CPU:         16–32 cores across 2+ servers
RAM:         32–64 GB
Disk:        NVMe SSD RAID-1, 1 TB
Load balancer: Nginx upstream / HAProxy
Gunicorn:    32–64 workers across 4–8 instances
Database:    PostgreSQL 15+ with streaming replication + failover
Cache:       Redis Cluster 7+
Task queue:  Celery 5+ + Redis (PDF, images, OREX simulation)
Monitoring:  Prometheus + Grafana
Logging:     Loki + Grafana or ELK stack
Backups:     Continuous replication + daily snapshots
```

---

## 7. Worker Count Reference

| Load | Workers | Threads | DB requirement |
|------|---------|---------|----------------|
| 5–10 users | 4–8 | 2 | SQLite (SSD strongly preferred) |
| 10–30 users | 8–12 | 3 | SQLite + SSD or PostgreSQL |
| 30–50 users | 12–16 | 4 | PostgreSQL required |
| 50–200 users | 16–32 | 4 | PostgreSQL + Redis + Celery |
| 200+ users | 32–64 distributed | 4 | Multi-server cluster |

**Formula used by autotuner:** `workers = (2 × CPU_cores) + 1`  
This is correct for **PostgreSQL**. For SQLite the safe maximum is **5–8 workers**.

---

## 8. Database Migration Path (SQLite → PostgreSQL)

```bash
# 1. Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# 2. Create database
sudo -u postgres psql -c "CREATE USER armguard WITH PASSWORD 'strongpassword';"
sudo -u postgres psql -c "CREATE DATABASE armguard_db OWNER armguard ENCODING 'UTF8';"

# 3. Install psycopg
pip install psycopg2-binary

# 4. Set environment variables (in .env or systemd unit)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=armguard_db
DB_USER=armguard
DB_PASSWORD=strongpassword
DB_HOST=localhost
DB_PORT=5432

# 5. Run migrations
python manage.py migrate

# 6. Transfer data (from SQLite backup)
# Use django-data-migration or a manual fixture export/import

# 7. Update gunicorn workers.env
# Workers can now be increased to (2 × CPU) + 1 = 25
```

---

## 9. Redis Setup (Cache + Session)

```bash
sudo apt install redis-server
sudo systemctl enable --now redis

# In .env
CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
CACHE_LOCATION=redis://127.0.0.1:6379/1
SESSION_ENGINE=django.contrib.sessions.backends.cache
SESSION_CACHE_ALIAS=default
```

Benefits:
- Atomic `incr()` — rate-limiter becomes accurate
- Sub-millisecond cache reads (vs. disk I/O with FileBasedCache)
- Session store: removes session writes from SQLite entirely

---

## 10. Monitoring Commands

```bash
# Watch Gunicorn live logs
journalctl -u armguard-gunicorn -f

# Check for "database is locked" errors (urgent signal)
journalctl -u armguard-gunicorn --since today | grep -i "database is locked"

# Database size and WAL status
sqlite3 /var/www/ARMGUARD_RDS_V1/project/db.sqlite3 "PRAGMA wal_checkpoint;"
ls -lh /var/www/ARMGUARD_RDS_V1/project/db.sqlite3*

# Disk I/O pressure (high await = HDD bottleneck)
iostat -x 2

# Worker memory usage
ps aux | grep gunicorn | awk '{sum+=$6} END {print sum/1024 " MB"}'

# Active Gunicorn connections
ss -tp | grep gunicorn | wc -l
```

---

## 11. Upgrade Priority Summary

| Upgrade | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Reduce workers 25 → 8 | High — eliminates lock queue | 5 min | **Do now** |
| Install Redis + update cache setting | High — fixes race conditions | 30 min | **Do now** |
| SSD storage | High — 10–50× I/O improvement | Hardware swap | **Soon** |
| PostgreSQL migration | Critical — row-level locking | 4–8 hours | **Within 2 weeks** |
| Celery for async tasks | Medium — unblocks request threads | 1–2 days | Month 2 |
| Async/batch ActivityLog writes | Medium — reduces write pressure | 2–4 hours | Month 2 |
| Multi-server setup | High — true horizontal scale | Multiple days | When needed |

---

## 12. Key Software Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Django | 6.0.3 | Web framework |
| Gunicorn | 22.0.0 | WSGI server |
| Pillow | 12.1.1 | Image processing (QR, ID cards, tags) |
| PyMuPDF (fitz) | 1.27.1 | PDF form filling + watermarking |
| qrcode | 8.2 | QR code generation |
| openpyxl | 3.1.5 | Excel import |
| gspread | 6.0.0 | Google Sheets import |
| WhiteNoise | — | Compressed static file serving |
| django-otp / django-two-factor-auth | — | TOTP MFA |
| djangorestframework | — | Read-only REST API |

---

*This document was generated from live code analysis of commit `0c8a270` on 2026-05-05.*
