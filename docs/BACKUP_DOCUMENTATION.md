# ArmGuard RDS V1 — Backup System Documentation

**Version:** 1.0  
**Date:** 2026-05-04  
**Environment:** Ubuntu Server 24.04 LTS · PostgreSQL 16 · Django 6.0.3  

---

## Table of Contents

1. [Overview](#1-overview)
2. [Backup Architecture](#2-backup-architecture)
3. [Components](#3-components)
   - [db_backup.py — Django Management Command](#31-db_backuppy--django-management-command)
   - [db-backup-cron.sh — Daily DB Cron Wrapper](#32-db-backup-cronsh--daily-db-cron-wrapper)
   - [backup.sh — Full Consolidated Backup](#33-backupsh--full-consolidated-backup)
   - [retrieve-backup.sh — Read-Only Backup Inspection](#34-retrieve-backupsh--read-only-backup-inspection)
   - [transfer-to-server.sh — Transfer & Recovery](#35-transfer-to-serversh--transfer--recovery)
4. [Backup Directory Structure](#4-backup-directory-structure)
5. [Cron Schedule](#5-cron-schedule)
6. [Retention Policy](#6-retention-policy)
7. [Integrity Verification (SHA-256)](#7-integrity-verification-sha-256)
8. [GPG Encryption (Optional)](#8-gpg-encryption-optional)
9. [External Drive Backup](#9-external-drive-backup)
10. [Security Notes](#10-security-notes)

---

## 1. Overview

The ArmGuard RDS V1 backup system provides three layers of protection:

| Layer | Script | Frequency | Who Runs It |
|-------|--------|-----------|-------------|
| **Database only** | `db-backup-cron.sh` → `db_backup.py` | Daily 02:00 | `armguard` user (cron) |
| **Full set** (DB + media + .env) | `backup.sh` | Every 3 hours | `root` (cron) |
| **Retrieval / inspection** | `retrieve-backup.sh` | On demand | Admin (root) |
| **Transfer / recovery** | `transfer-to-server.sh` | On demand | Admin (root) |

**What is backed up in a full backup:**

- PostgreSQL database dump (compressed, `.sql.gz`)
- `project/media/` — all user-uploaded files (`.tar.gz`)
- `.env` — application configuration and secrets (plaintext or GPG-encrypted)

---

## 2. Backup Architecture

```
Production Server (192.168.0.162)
│
├── /var/www/ARMGUARD_RDS_V1/
│   └── scripts/
│       ├── db-backup-cron.sh      ← armguard user cron (daily, DB only)
│       ├── backup.sh              ← root cron (every 3h, full set)
│       ├── retrieve-backup.sh     ← on-demand inspection
│       └── transfer-to-server.sh  ← on-demand transfer/recovery
│
├── /var/backups/armguard/         ← Local backup store (chmod 700, root-only)
│   └── YYYYMMDD_HHMMSS/
│       ├── armguard_backup_TIMESTAMP.sql.gz
│       ├── armguard_backup_TIMESTAMP.sql.gz.sha256
│       ├── media_TIMESTAMP.tar.gz
│       └── env_TIMESTAMP.env
│
└── /mnt/backup/armguard/          ← External drive (optional, rsync copy)
    └── YYYYMMDD_HHMMSS/
        └── (same structure)

                   │ rsync (transfer-to-server.sh)
                   ▼
Target Server (e.g. 192.168.0.200)
└── /var/backups/armguard/YYYYMMDD_HHMMSS/  ← staged here, then restored
```

---

## 3. Components

### 3.1 `db_backup.py` — Django Management Command

**Location:** `project/armguard/apps/users/management/commands/db_backup.py`

The core backup engine. Called by both cron wrappers. Detects the configured database engine and acts accordingly:

#### PostgreSQL (production)

- Runs `pg_dump -F p` (plain SQL format) on the `armguard` database
- Pipes output through `gzip` → `armguard_backup_TIMESTAMP.sql.gz`
- Writes SHA-256 checksum sidecar → `armguard_backup_TIMESTAMP.sql.gz.sha256`
- Logs the event via `log_system_event()` (audit trail in DB)
- Rotates old backups — keeps the N most recent (default: 10)

#### SQLite (development only)

- Uses `sqlite3.Connection.backup()` — safe hot-copy under concurrent access
- Output: `armguard_backup_TIMESTAMP.sqlite3`
- Checksum sidecar: `armguard_backup_TIMESTAMP.sha256`
- Old backups are overwritten with zeros before deletion (`_secure_delete()`)

**CLI usage:**

```bash
# Default output to <project>/backups/, keep last 10
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
    /var/www/ARMGUARD_RDS_V1/project/manage.py db_backup

# Custom output directory, keep last 14
sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
    /var/www/ARMGUARD_RDS_V1/project/manage.py db_backup \
    --output /var/backups/armguard --keep 14
```

---

### 3.2 `db-backup-cron.sh` — Daily DB Cron Wrapper

**Location:** `scripts/db-backup-cron.sh`  
**Run as:** `armguard` user  
**Purpose:** Thin wrapper around `db_backup.py` for the daily 02:00 cron job.

Key behaviors:

- Sources `.env` to export `DB_*` variables before invoking Django
- Sets `DJANGO_SETTINGS_MODULE=armguard.settings.production`
- Appends output to `/var/log/armguard/backup.log`
- Reports backup count and directory size after completion
- **Does not use `sudo`** — runs directly as `armguard` (no sudo privilege required)

**Log location:** `/var/log/armguard/backup.log`

---

### 3.3 `backup.sh` — Full Consolidated Backup

**Location:** `scripts/backup.sh`  
**Run as:** `root`  
**Purpose:** Every-3-hour full backup of DB + media + .env, with optional GPG encryption and external drive sync.

**Steps performed:**

| Step | Action | Output |
|------|--------|--------|
| 1 | Database backup via `db_backup` Django command | `armguard_backup_TIMESTAMP.sql.gz` + `.sha256` |
| 2 | Archive `project/media/` | `media_TIMESTAMP.tar.gz` |
| 3 | Copy `.env` | `env_TIMESTAMP.env` |
| 4 (opt) | GPG-encrypt entire backup dir | `armguard_backup_TIMESTAMP.tar.gz.gpg` |
| 5 (opt) | rsync to external drive at `/mnt/backup` | Mirror of local backup |
| 6 | Rotate local backups older than `KEEP_DAYS` (default: 7) | — |

**Priority controls:** The script self-limits using `renice -n 19` (lowest CPU) and `ionice -c 3` (idle I/O) so backup I/O never competes with web worker I/O.

**Backup root permissions:** `chmod 700 /var/backups/armguard` — root-only read/write, protecting the plaintext `.env` copy.

**Flags:**

```bash
sudo bash scripts/backup.sh              # normal run
sudo bash scripts/backup.sh --dry-run    # show what would run, write nothing
sudo bash scripts/backup.sh --keep 14   # override retention (14 days)
```

---

### 3.4 `retrieve-backup.sh` — Read-Only Backup Inspection

**Location:** `scripts/retrieve-backup.sh`  
**Run as:** `root`  
**Purpose:** Safely inspect any backup in a temporary PostgreSQL database **without touching the live `armguard` database**.

**How it works:**

1. Lists available backups from `/var/backups/armguard/` and `/mnt/backup/armguard/`
2. Verifies SHA-256 checksum of the selected dump
3. Creates a temporary database: `armguard_retrieve_TIMESTAMP`
4. Loads the `.sql.gz` dump into the temp DB via `gunzip | psql`
5. Opens interactive `psql` connected to the temp DB (or runs `--query`)
6. On exit (even on error), a `trap` automatically drops the temp DB

The live production database is **never modified**.

**Flags:**

```bash
sudo bash scripts/retrieve-backup.sh
sudo bash scripts/retrieve-backup.sh --backup /var/backups/armguard/20260504_072232
sudo bash scripts/retrieve-backup.sh --query "SELECT * FROM personnel_personnel LIMIT 10"
sudo bash scripts/retrieve-backup.sh --query "SELECT ..." --export /tmp/results.csv
```

---

### 3.5 `transfer-to-server.sh` — Transfer & Recovery

**Location:** `scripts/transfer-to-server.sh`  
**Run as:** `root`  
**Purpose:** Copy a backup set from this server to a target server via `rsync`/SSH, then restore the full application there.

**Three operating modes:**

| Mode | Flag | Description |
|------|------|-------------|
| Transfer + Restore | *(default)* | Copy files then immediately restore on target |
| Transfer Only | `--transfer-only` | Copy files; restore manually later |
| Restore Only | `--restore-only` | Run restore directly on target (no SSH needed) |

**What the restore does on the target:**

1. Verifies SHA-256 checksum of the dump
2. Loads DB credentials from `.env` (if present)
3. Creates the `armguard` PostgreSQL role if it doesn't exist
4. Stops `armguard-gunicorn`
5. Drops and recreates the `armguard` database
6. Restores the `.sql.gz` dump via `gunzip | psql`
7. Extracts `media_TIMESTAMP.tar.gz` → `project/media/` (backs up existing media first)
8. Copies `env_TIMESTAMP.env` → `.env` (backs up existing `.env` first)
9. Fixes file ownership: `chown -R armguard:armguard /var/www/ARMGUARD_RDS_V1`
10. Runs `manage.py migrate` to apply any unapplied migrations
11. Starts `armguard-gunicorn`

**Flags:**

```bash
--target USER@IP    Target server (required unless --restore-only)
--backup  DIR       Specific backup directory (skip menu)
--transfer-only     Copy only; skip restore
--restore-only      Restore only; skip transfer (run on target directly)
--skip-env          Do not copy/restore the .env file
--skip-media        Do not transfer/restore media files
--port    PORT      SSH port (default: 22)
--key     FILE      SSH private key path
```

---

## 4. Backup Directory Structure

Each backup set is stored in a timestamped directory:

```
/var/backups/armguard/
└── 20260504_020000/                         ← Timestamp: YYYYMMDD_HHMMSS
    ├── armguard_backup_20260504_020001.sql.gz       ← PostgreSQL dump (compressed)
    ├── armguard_backup_20260504_020001.sql.gz.sha256  ← SHA-256 checksum
    ├── media_20260504_020000.tar.gz                 ← media/ archive
    └── env_20260504_020000.env                      ← .env copy (chmod 600)
```

If GPG encryption is enabled, the entire directory is archived and encrypted:

```
/var/backups/armguard/
├── armguard_backup_20260504_020000.tar.gz.gpg    ← Encrypted archive
└── (plaintext directory is removed after encryption)
```

---

## 5. Cron Schedule

Cron jobs installed by `deploy.sh`:

| Cron user | Schedule | Script | Description |
|-----------|----------|--------|-------------|
| `armguard` | `0 2 * * *` | `db-backup-cron.sh` | Daily DB backup at 02:00 |
| `root` | `0 */3 * * *` | `backup.sh` | Full backup every 3 hours |
| `root` | `0 3 1 * *` | `renew-ssl-cert.sh` | SSL cert renewal, 1st of month |
| `root` | `0 3 * * *` | `purge_camera_uploads` | Daily camera file purge |

The every-3-hour backup runs at: `00:00 03:00 06:00 09:00 12:00 15:00 18:00 21:00`

**Check installed cron jobs:**

```bash
sudo crontab -l          # root crons
crontab -u armguard -l   # armguard user crons
```

---

## 6. Retention Policy

| Storage | Default Retention | Override |
|---------|------------------|----------|
| `backup.sh` local backups | 7 days | `--keep N` |
| `backup.sh` external drive | 7 days | (same `--keep N`) |
| `db-backup-cron.sh` | 14 days | Edit `KEEP_DAYS` in script |
| `db_backup.py` (direct) | 10 files | `--keep N` |

Old backup sets are deleted when a new backup runs and the oldest set exceeds `KEEP_DAYS`.

---

## 7. Integrity Verification (SHA-256)

Every database dump is accompanied by a `.sha256` sidecar file:

```
armguard_backup_20260504_020001.sql.gz
armguard_backup_20260504_020001.sql.gz.sha256   ← contains: <hash>  <filename>
```

The sidecar format is compatible with `sha256sum -c`:

```bash
# Manual verification
cd /var/backups/armguard/20260504_020000
sha256sum -c armguard_backup_20260504_020001.sql.gz.sha256
# → armguard_backup_20260504_020001.sql.gz: OK
```

SHA-256 is a deterministic, machine-agnostic hash. The same bytes always produce the same hash on any server — there is no server-specific salt or secret. The hash verifies **file integrity** only; it is not encryption.

Both `retrieve-backup.sh` and `transfer-to-server.sh` verify the checksum automatically before proceeding. A mismatch produces a warning and prompts for confirmation; it does not silently proceed.

---

## 8. GPG Encryption (Optional)

If `ARMGUARD_BACKUP_GPG_RECIPIENT` is set in `.env`, `backup.sh` will:

1. Create a `.tar.gz` archive of the entire backup directory
2. Encrypt it with the specified GPG key: `gpg --recipient <key-id> --encrypt`
3. Shred (overwrite with zeros) the plaintext archive
4. Delete the plaintext backup directory

**Setup:**

```bash
# Import your GPG public key on the server
gpg --import /path/to/your-key.asc

# Add to .env
ARMGUARD_BACKUP_GPG_RECIPIENT=your-key-id-or-email

# Verify
gpg --list-keys
```

**Without GPG:** The backup root is `chmod 700` (root-only). The `.env` copy is `chmod 600`. These are minimum safeguards — GPG encryption is strongly recommended in production.

---

## 9. External Drive Backup

The backup system supports automatic mirroring to a mounted external drive.

**Drive details (production server):**

| Field | Value |
|-------|-------|
| Device | `/dev/sdb3` |
| UUID | `ff28a2b1-df2f-402b-9b88-38133225a40f` |
| Label | `RDSDRIVEL` |
| Capacity | 672 GB |
| Mount point | `/mnt/backup` |
| Format | ext4 |

**fstab entry** (auto-mount with `nofail` — server boots even if drive is absent):

```
UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup ext4 defaults,nofail 0 2
```

**Setup via deploy.sh:**

```bash
sudo bash scripts/deploy.sh --external-drive
```

**Manual mount:**

```bash
sudo mount /dev/sdb3 /mnt/backup
mountpoint -q /mnt/backup && echo "mounted" || echo "not mounted"
```

If the drive is not mounted when `backup.sh` runs, the external backup step is skipped with a warning; the local backup still completes normally.

---

## 10. Security Notes

| Risk | Mitigation |
|------|-----------|
| Backup root readable by non-root | `/var/backups/armguard` is `chmod 700` |
| `.env` in plaintext backup | `env_*.env` files are `chmod 600`; GPG recommended |
| Database dump contains all data | `.sql.gz` files are root-only; GPG recommended |
| Tampered backup transferred via network | SHA-256 checksum verified before restore |
| Restore overwrites wrong server | `--restore-only` asks confirmation on checksum mismatch |
| `.env` wrong after transfer | Script backs up existing `.env` before overwriting; prompts review |
| armguard user privilege escalation | `db-backup-cron.sh` runs as armguard with no sudo — cannot escalate |
| pg_dump credential leak | `PGPASSWORD` exported only in subprocess scope; unset after use |
