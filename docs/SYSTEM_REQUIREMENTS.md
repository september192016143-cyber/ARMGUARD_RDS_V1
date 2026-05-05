# ArmGuard RDS V1 — System Requirements & Storage Planning

**Version:** 1.0
**Date:** 2026-05-06
**Environment:** Ubuntu Server 24.04 LTS · Production server: `192.168.0.162`

---

## Table of Contents

1. [Hardware Requirements](#1-hardware-requirements)
2. [Current Server Specifications](#2-current-server-specifications)
3. [Storage Growth Estimates](#3-storage-growth-estimates)
   - [Database (SQLite)](#31-database-sqlite)
   - [Media Files](#32-media-files)
   - [Projected Totals](#33-projected-totals)
4. [Automatic Maintenance — ActivityLog Purge](#4-automatic-maintenance--activitylog-purge)
5. [Software Requirements](#5-software-requirements)
6. [Network Requirements](#6-network-requirements)
7. [Scaling Notes](#7-scaling-notes)

---

## 1. Hardware Requirements

### Minimum Specification

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores / 8 threads | 6 cores / 12 threads |
| **RAM** | 8 GB | 16 GB |
| **Primary Storage** | **SSD 120 GB** | SSD 256 GB |
| **Backup Storage** | External HDD 500 GB | External HDD 1 TB |
| **Network** | 100 Mbps LAN | 1 Gbps LAN |
| **OS** | Ubuntu Server 22.04 LTS | Ubuntu Server 24.04 LTS |

> **SSD is the most critical requirement.** ArmGuard uses SQLite, which holds a
> file-level write lock during every INSERT/UPDATE. On HDD, lock contention
> between concurrent Gunicorn workers can cause intermittent
> `OperationalError: database is locked`. An SSD reduces lock hold time by 10–30×,
> effectively eliminating this error class at normal load.

### Why These Numbers

| Factor | Explanation |
|--------|-------------|
| **CPU** | Pillow ID card PNG generation (~1–2s burst), PyMuPDF TR PDF generation (~0.5s burst), OREX simulation background thread (~10 min, 1 DB write/5s). Bursts are short; low sustained CPU need. |
| **RAM** | Gunicorn formula: `(CPUs × 2) + 1` workers × ~100 MB RSS each. 6-core server = 13 workers × 100 MB = 1.3 GB workers + 1 GB OS + 1 GB Django overhead ≈ 4 GB peak. 8 GB provides comfortable headroom. |
| **SSD** | SQLite write lock duration scales directly with disk write speed. See note above. |
| **Backup HDD** | 3-hourly SQLite snapshots (12 MB each) = ~96 MB/day. 1 TB covers 28+ years of backups with no rotation. |

---

## 2. Current Server Specifications

| Component | Value |
|-----------|-------|
| Logical CPUs | 12 |
| RAM | 15,852 MB (~16 GB) |
| Primary disk type | **HDD** (ROTA=1) |
| Primary disk size | 226 GB |
| Disk used | 9.9 GB (5%) |
| Gunicorn workers | 25 (auto-tuned) |
| Gunicorn threads | 4 per worker (HDD mode) |
| Django WSGI service | `armguard-gunicorn` (systemd) |
| Web server | Nginx (SSL) |

> The current server **exceeds the recommended spec** on CPU and RAM. The only
> weakness is the HDD — consider adding an SSD for the OS/app partition if
> SQLite lock errors recur under heavier load.

---

## 3. Storage Growth Estimates

Baseline measurements taken from live server on 2026-05-06:

| Area | Current | Est. 1 Year | Est. 3 Years |
|------|---------|-------------|--------------|
| Database (SQLite) | 12 MB | 72 MB | 212 MB |
| Media files | 313 MB | 433 MB | 673 MB |
| **Total** | **325 MB** | **505 MB** | **885 MB** |

### 3.1 Database (SQLite)

Growth is dominated by **ActivityLog** (one row per HTTP request):

| Table | Est. Row Size | Growth Driver |
|-------|--------------|---------------|
| `ActivityLog` | ~0.6 KB | Every HTTP request — ~1,250 rows/day at 25 users |
| `AuditLog` | ~0.8 KB | Every CRUD, login, logout (~5–15 per transaction) |
| `Transaction` | ~1.5 KB | 228 rows per full OREX cycle (114 withdraw + 114 return) |
| `TransactionLogs` | ~2 KB | 1 row per transaction |
| `SimulationRun` | ~50 KB | Stores full JSON results per simulation run |
| `Personnel` | ~2 KB | Static — ~114 rows |
| `Pistol` / `Rifle` | ~1.5 KB | Static inventory |
| `AnalyticsSnapshot` | ~3 KB | Periodic snapshots |

**ActivityLog without purge:** ~270 MB/year
**ActivityLog with 1-year purge:** stabilises at ~270 MB steady state (oldest rows deleted as new ones arrive)

### 3.2 Media Files

| Folder | Per Item | Current | Growth Driver |
|--------|----------|---------|---------------|
| `personnel_id_cards/` | ~450 KB/person (front + back PNG) | 101 MB | Regenerated on demand; stable at ~450 KB × personnel count |
| `TR_PDF/` | ~80 KB/PDF | 25 MB | 1 file per TR transaction print |
| `personnel_images/` | ~160 KB/photo | 37 MB | User-uploaded; grows with roster |
| `item_id_tags/` | ~15 KB/tag PNG | 32 MB | Per pistol/rifle; stable once all items tagged |
| `qr_code_images_pistol/` | ~5 KB/QR | 13 MB | Per pistol; stable |
| `qr_code_images_rifle/` | ~5 KB/QR | 4.3 MB | Per rifle; stable |
| `qr_code_images_personnel/` | ~5 KB/QR | 2.5 MB | Per person; stable |
| `serial_capture_temp/` | ~500 KB/capture | 100 MB | **Purged daily** by cron (5-day retention) |
| `REPORT_PDF/` | Streamed in memory | ~4 KB | Not persisted to disk |

**Largest grower: `TR_PDF/`** — accumulates indefinitely. At 1 OREX cycle/month
(114 TRs printed) = ~9 MB/month = ~110 MB/year.
Consider a periodic purge of TR PDFs older than 1 year if disk space becomes a concern.

### 3.3 Projected Totals

| Period | DB growth | Media growth | Total added |
|--------|-----------|--------------|-------------|
| Per OREX cycle | ~1.5 MB | ~8 MB | ~10 MB |
| Per month | ~5 MB | ~10 MB | ~15 MB |
| Per year | ~60 MB | ~120 MB | **~180 MB** |
| 3 years | ~200 MB | ~400 MB | **~600 MB** |

On the current 226 GB disk at 5% utilisation, there is **no foreseeable storage concern**
for the lifetime of this deployment.

---

## 4. Automatic Maintenance — ActivityLog Purge

To prevent the `ActivityLog` table from growing without bound, a daily purge
job is installed automatically by `update-server.sh`:

| Property | Value |
|----------|-------|
| Command | `python manage.py purge_activity_logs` |
| Schedule | Daily at **03:30** (cron) |
| Retention | **365 days** (1 year) |
| Log file | `/var/log/armguard/purge_activity_logs.log` |
| Source | `project/armguard/apps/users/management/commands/purge_activity_logs.py` |

**Effect:** Any `ActivityLog` row whose `timestamp` is older than 1 year is
deleted automatically. The table stabilises at ~270 MB rather than growing
indefinitely.

To run manually:
```bash
# Dry-run — preview what would be deleted
sudo -u rds /var/www/ARMGUARD_RDS_V1/venv/bin/python \
    /var/www/ARMGUARD_RDS_V1/project/manage.py purge_activity_logs --dry-run

# Live run
sudo -u rds /var/www/ARMGUARD_RDS_V1/venv/bin/python \
    /var/www/ARMGUARD_RDS_V1/project/manage.py purge_activity_logs
```

To verify the cron is installed:
```bash
crontab -l | grep purge_activity_logs
```

---

## 5. Software Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.12+ | Required for Django 6.0.3 |
| Django | 6.0.3 | |
| Gunicorn | Latest | `gthread` worker class |
| Nginx | Latest | SSL termination |
| Pillow | 12.1.1+ | ID card PNG generation |
| PyMuPDF (fitz) | Latest | Daily report PDF generation |
| qrcode | Latest | QR code generation |
| django-otp | Latest | TOTP two-factor authentication |
| SQLite | 3.x (bundled) | No separate install required |
| fontconfig | Latest | Auto-installed by `update-server.sh` |
| fonts-liberation | Latest | Arial Nova fallback font (auto-installed via apt) |

---

## 6. Network Requirements

| Requirement | Value |
|-------------|-------|
| LAN speed | 100 Mbps minimum (1 Gbps recommended) |
| Server IP | `192.168.0.162` (static, LAN only) |
| HTTPS port | 443 (Nginx, self-signed SSL) |
| HTTP port | 80 (redirects to HTTPS) |
| Gunicorn port | 8000 (localhost only — not exposed externally) |
| Internet access | Required only for `update-server.sh` (git pull, apt, pip) |
| DNS | Not required — LAN IP access only |

ArmGuard is designed as an **air-gapped LAN application**. It does not require
internet access during normal operation.

---

## 7. Scaling Notes

### When to consider migrating from SQLite to PostgreSQL

| Trigger | Threshold |
|---------|-----------|
| Concurrent active users | > 50 simultaneous |
| `OperationalError: database is locked` errors recurring | After SSD upgrade applied |
| Database size | > 1 GB |
| OREX simulation frequency | > 1 run per hour |

### Gunicorn auto-tuning

`update-server.sh` runs `gunicorn-autoconf.sh` on every deploy, which sets:
- **Workers** = `(logical CPUs × 2) + 1`, capped by RAM
- **Threads** = 2 (SSD) or 4 (HDD)

No manual tuning is needed when hardware changes — redeploy and the script
recalculates automatically.

### Worker recycling

Worker recycling (`max_requests`) is **disabled** (`max_requests=0`) because the
OREX simulation background thread can run for ~10 minutes. If a worker is
recycled mid-simulation, the thread is killed and the `SimulationRun` record
stays stuck in `running` state. This is safe for an internal low-traffic
application.
