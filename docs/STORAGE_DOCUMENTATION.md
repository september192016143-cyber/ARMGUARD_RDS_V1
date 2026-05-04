# ArmGuard RDS V1 — Storage Mounting Documentation

**Version:** 1.0  
**Date:** 2026-05-04  
**Environment:** Ubuntu Server 24.04 LTS · Production server: `192.168.0.162`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Storage Layout](#2-storage-layout)
3. [Root Disk — LVM Setup](#3-root-disk--lvm-setup)
   - [LVM Auto-Expand](#31-lvm-auto-expand)
4. [External Backup Drive](#4-external-backup-drive)
   - [Drive Details](#41-drive-details)
   - [Mount Point](#42-mount-point)
   - [fstab Entry](#43-fstab-entry)
   - [Directory Structure on Drive](#44-directory-structure-on-drive)
5. [Automated Setup via deploy.sh](#5-automated-setup-via-deploysh)
   - [_setup_external_drive() Behavior](#51-_setup_external_drive-behavior)
6. [Mount Options Explained](#6-mount-options-explained)
7. [Filesystem Permissions](#7-filesystem-permissions)
8. [Backup Storage Paths](#8-backup-storage-paths)
9. [Disk Monitoring](#9-disk-monitoring)
10. [Security Notes](#10-security-notes)

---

## 1. Overview

The ArmGuard server uses two storage volumes:

| Volume | Purpose | Location |
|--------|---------|----------|
| **Root disk** | OS, app code, logs, local backups | `/` (LVM, ext4) |
| **External drive** | Long-term redundant backup copies | `/mnt/backup` (ext4) |

The external drive is optional — the application functions fully without it. When mounted, `backup.sh` automatically mirrors every backup set to it via `rsync`.

---

## 2. Storage Layout

```
┌─────────────────────────────────────────────────────┐
│ Root Disk (LVM)                                     │
│                                                     │
│  /                           ← OS, app, venv        │
│  /var/www/ARMGUARD_RDS_V1/   ← Application root     │
│  /var/backups/armguard/      ← Local backup store   │
│  /var/log/armguard/          ← Application logs     │
│  /etc/nginx/                 ← Nginx config         │
│  /etc/systemd/system/        ← Gunicorn service     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ External Backup Drive (ext4)                        │
│                                                     │
│  /mnt/backup/                ← Mount point (root)   │
│  /mnt/backup/armguard/       ← rsync backup mirror  │
│    └── YYYYMMDD_HHMMSS/      ← Timestamped sets     │
└─────────────────────────────────────────────────────┘
```

---

## 3. Root Disk — LVM Setup

The production server uses LVM (Logical Volume Manager) on its root disk. This allows the root filesystem to be expanded without rebooting when new disk space is added.

### LVM component hierarchy

```
Physical Volumes (PVs) → Volume Group (VG) → Logical Volumes (LVs)
       sda                  ubuntu-vg             ubuntu-lv  (/)
```

**Check current LVM status:**

```bash
sudo pvs          # Physical volumes
sudo vgs          # Volume groups
sudo lvs          # Logical volumes
df -h /           # Root filesystem usage
```

### 3.1 LVM Auto-Expand

`update-server.sh` runs `_expand_lvm()` at startup. This function:

1. Detects whether root is LVM (`/dev/mapper/*`)
2. Runs `pvresize` on all physical volumes to pick up any new disk space
3. Checks `vg_free` — free space in the volume group
4. If free space exists, runs `lvextend -l +100%FREE` to grow the LV
5. Runs `resize2fs` (ext4) or `xfs_growfs` (XFS) to extend the filesystem

This is a **non-destructive, no-reboot** operation. If it fails, the update continues normally.

**Manual expansion (if needed):**

```bash
# After adding disk space via hypervisor or replacing disk:
sudo pvresize /dev/sda
sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
sudo resize2fs /dev/ubuntu-vg/ubuntu-lv
df -h /   # Verify new size
```

---

## 4. External Backup Drive

### 4.1 Drive Details

| Field | Value |
|-------|-------|
| Device path | `/dev/sdb3` |
| UUID | `ff28a2b1-df2f-402b-9b88-38133225a40f` |
| Label | `RDSDRIVEL` |
| Capacity | 672 GB |
| Filesystem | ext4 |
| Mount point | `/mnt/backup` |

### 4.2 Mount Point

The mount point `/mnt/backup` is created by `deploy.sh` with the following permissions:

```
drwxr-x--- root root  /mnt/backup    (chmod 750)
drwxr-x--- root root  /mnt/backup/armguard/
```

Only `root` can write to the backup drive. The `armguard` application user cannot write directly to the external drive — all external backup writes go through `backup.sh` which runs as root.

### 4.3 fstab Entry

The drive is registered in `/etc/fstab` for automatic mounting at boot. The `nofail` option ensures the server boots normally even if the drive is absent or fails.

**fstab line (written by `deploy.sh --external-drive`):**

```
UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup ext4 defaults,nofail,noatime 0 2
```

| Option | Meaning |
|--------|---------|
| `defaults` | rw, suid, dev, exec, auto, nouser, async |
| `nofail` | Boot continues if drive is absent or fails to mount |
| `noatime` | Do not update access timestamps — reduces unnecessary write I/O |
| `0` (dump) | Do not include in dump backup utility |
| `2` (pass) | fsck pass order: check after root filesystem (pass 1) |

### 4.4 Directory Structure on Drive

```
/mnt/backup/
└── armguard/                              ← created by deploy.sh
    ├── 20260504_020000/                   ← rsync'd from /var/backups/armguard/
    │   ├── armguard_backup_*.sql.gz
    │   ├── armguard_backup_*.sql.gz.sha256
    │   ├── media_*.tar.gz
    │   └── env_*.env
    ├── 20260504_050000/
    └── ...
```

---

## 5. Automated Setup via deploy.sh

### 5.1 `_setup_external_drive()` Behavior

When `deploy.sh` is run with the `--external-drive` flag, it calls `_setup_external_drive()` which:

**Step 1 — Detect candidate drives**

- Reads `lsblk -rno NAME,SIZE,TYPE,FSTYPE,LABEL`
- Excludes the root disk and its partitions
- Excludes loop, rom, and ram devices
- Excludes already-mounted devices
- Presents numbered menu of candidates

**Step 2 — Format (if blank drive)**

- If the selected device has no filesystem, prompts for confirmation
- Formats as `ext4` with label `ARMGUARD_BCK`:
  ```bash
  mkfs.ext4 -L ARMGUARD_BCK -F /dev/sdX
  ```
- Existing filesystems (ext4, xfs, btrfs) are used as-is

**Step 3 — fstab registration**

- Reads UUID via `blkid -o value -s UUID`
- Backs up existing fstab: `/etc/fstab.bak.TIMESTAMP`
- Appends the appropriate mount line (ext4/xfs/btrfs-aware options)
- Skips if UUID already present in fstab

**Step 4 — Mount now**

- Runs `mount /dev/sdX /mnt/backup`
- Creates `/mnt/backup/armguard/` subdirectory

**Step 5 — Update backup.sh**

- Replaces the default UUID placeholder in `backup.sh` with the actual UUID of the chosen drive

---

## 6. Mount Options Explained

### For external backup drive (ext4)

| Option | Why |
|--------|-----|
| `nofail` | Critical — prevents boot hang if drive is unplugged or fails |
| `noatime` | Backup reads don't update file access time → less write wear |
| `defaults` | Standard rw mount |

### For root LVM volume (managed by Ubuntu installer)

Typical fstab line for LVM root:

```
/dev/mapper/ubuntu--vg-ubuntu--lv / ext4 errors=remount-ro 0 1
```

| Option | Why |
|--------|-----|
| `errors=remount-ro` | On filesystem error, remount read-only to prevent corruption |
| `0 1` | fsck pass 1 (first to be checked) |

---

## 7. Filesystem Permissions

| Path | Owner | Mode | Notes |
|------|-------|------|-------|
| `/var/backups/armguard/` | `root:root` | `700` | Root-only; protects plaintext .env copies |
| `/mnt/backup/` | `root:root` | `750` | Root write, readable by root group |
| `/mnt/backup/armguard/` | `root:root` | `755` | rsync destination |
| `/var/www/ARMGUARD_RDS_V1/` | `armguard:armguard` | `755` | App files |
| `/var/www/ARMGUARD_RDS_V1/.env` | `root:armguard` | `640` | Root owns, armguard reads |
| `/var/log/armguard/` | `armguard:armguard` | `755` | App log directory |

---

## 8. Backup Storage Paths

| Path | Managed by | Retention |
|------|-----------|-----------|
| `/var/backups/armguard/` | `backup.sh` (root cron) | 7 days default |
| `/var/www/ARMGUARD_RDS_V1/backups/` | `db-backup-cron.sh` (armguard cron) | 14 days default |
| `/mnt/backup/armguard/` | `backup.sh` rsync step | 7 days default |

The `db-backup-cron.sh` path (`/var/www/ARMGUARD_RDS_V1/backups/`) is written by the `armguard` user because it lives inside the app directory. The `backup.sh` path (`/var/backups/armguard/`) is written by root.

---

## 9. Disk Monitoring

### Check disk usage

```bash
df -h                         # All mounted filesystems
df -h / /mnt/backup           # Root + external drive
du -sh /var/backups/armguard/ # Local backup store size
du -sh /mnt/backup/armguard/  # External drive usage
```

### Check inode usage (can fill up independently of space)

```bash
df -i /
df -i /mnt/backup
```

### Check mount status

```bash
lsblk                                          # All block devices
findmnt                                        # All active mounts
mountpoint -q /mnt/backup && echo "mounted"    # Check external drive
```

### Check LVM free space

```bash
sudo vgs                 # Free space in volume group
sudo lvs -o +devices     # LV → device mapping
```

### Identify drive UUIDs

```bash
sudo blkid               # All devices with UUIDs
lsblk -o NAME,UUID,FSTYPE,LABEL,SIZE,MOUNTPOINT
```

---

## 10. Security Notes

| Risk | Mitigation |
|------|-----------|
| Drive stolen — data exposed | GPG-encrypt backups before writing to drive (set `ARMGUARD_BACKUP_GPG_RECIPIENT` in `.env`) |
| Drive replaced — wrong UUID in fstab | `nofail` prevents boot hang; monitor with `mountpoint -q /mnt/backup` |
| Root fills up — app crashes | Monitor with `df -h /`; LVM auto-expand in `update-server.sh` handles most cases |
| World-readable backup files | `/var/backups/armguard` is `chmod 700`; `/mnt/backup` is `chmod 750` |
| fstab corruption | `deploy.sh` backs up `/etc/fstab` to `/etc/fstab.bak.TIMESTAMP` before every edit |
| Noisy write I/O during backup | `backup.sh` uses `noatime` + `ionice -c 3` (idle I/O class) |
