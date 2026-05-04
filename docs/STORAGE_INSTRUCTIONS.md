# ArmGuard RDS V1 — Storage Mounting Instructions

**Server:** `192.168.0.162` · User: `rds` (sudo) · Ubuntu 24.04 LTS

---

## Quick Reference

| Task | Command |
|------|---------|
| Check if external drive is mounted | `mountpoint -q /mnt/backup && echo "MOUNTED" \|\| echo "NOT MOUNTED"` |
| Mount external drive manually | `sudo mount /dev/sdb3 /mnt/backup` |
| Unmount external drive | `sudo umount /mnt/backup` |
| List all block devices + UUIDs | `lsblk -o NAME,UUID,FSTYPE,LABEL,SIZE,MOUNTPOINT` |
| Show disk usage | `df -h` |
| Show LVM free space | `sudo vgs` |
| Expand root LVM to fill disk | `sudo pvresize /dev/sda ; sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv ; sudo resize2fs /dev/ubuntu-vg/ubuntu-lv` |
| View fstab | `cat /etc/fstab` |
| Test fstab without rebooting | `sudo mount -a` |
| Format a blank drive as ext4 | `sudo mkfs.ext4 -L ARMGUARD_BCK -F /dev/sdX` |

---

## 1. Auto-Configure the External Backup Drive (Recommended)

Run `deploy.sh` with the `--external-drive` flag. It detects available drives, offers a menu, formats if blank, and writes the fstab entry automatically.

```bash
cd /var/www/ARMGUARD_RDS_V1
sudo bash scripts/deploy.sh --external-drive
```

The script will:
1. List all non-root, unmounted drives
2. Let you select one
3. Format it as ext4 (if blank) — **erases all data**, confirmation required
4. Create `/mnt/backup/` and `/mnt/backup/armguard/`
5. Add the UUID-based fstab entry with `nofail,noatime`
6. Mount it immediately
7. Update `backup.sh` with the correct UUID

---

## 2. Manual External Drive Setup

Use this if you prefer to configure the drive yourself or if `deploy.sh` is not available.

### Step 1 — Identify the drive

```bash
lsblk -o NAME,UUID,FSTYPE,LABEL,SIZE,MOUNTPOINT
sudo blkid
```

Find your external drive (e.g. `/dev/sdb`, `/dev/sdb3`). Note the device path and UUID.

### Step 2 — Format the drive (only if blank / new drive)

> **Warning:** This erases all existing data on the drive.

```bash
sudo mkfs.ext4 -L ARMGUARD_BCK -F /dev/sdb3
```

Verify the format:

```bash
sudo blkid /dev/sdb3
# Output example:
# /dev/sdb3: LABEL="ARMGUARD_BCK" UUID="ff28a2b1-..." TYPE="ext4"
```

### Step 3 — Create the mount point

```bash
sudo mkdir -p /mnt/backup
sudo chmod 750 /mnt/backup
```

### Step 4 — Get the UUID

```bash
sudo blkid -o value -s UUID /dev/sdb3
# ff28a2b1-df2f-402b-9b88-38133225a40f
```

### Step 5 — Back up and edit fstab

```bash
sudo cp /etc/fstab /etc/fstab.bak.$(date +%Y%m%d)
sudo nano /etc/fstab
```

Add this line at the end (replace UUID with yours):

```
UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup ext4 defaults,nofail,noatime 0 2
```

### Step 6 — Test fstab and mount

```bash
sudo mount -a          # applies all fstab entries
mountpoint -q /mnt/backup && echo "OK — mounted" || echo "FAILED"
df -h /mnt/backup
```

### Step 7 — Create the armguard subdirectory

```bash
sudo mkdir -p /mnt/backup/armguard
```

---

## 3. Mount / Unmount the External Drive

### Mount

```bash
# Using device path
sudo mount /dev/sdb3 /mnt/backup

# Using UUID (more reliable — device name can change)
sudo mount UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup

# Mount all fstab entries (including the external drive if in fstab)
sudo mount -a
```

### Unmount (before physically removing the drive)

```bash
sudo umount /mnt/backup
```

If the drive is busy:

```bash
# Find what's using it
sudo lsof /mnt/backup

# Force unmount (only if nothing critical is writing)
sudo umount -l /mnt/backup
```

### Check mount status

```bash
mountpoint -q /mnt/backup && echo "MOUNTED" || echo "NOT MOUNTED"
df -h /mnt/backup
```

---

## 4. LVM Root Disk Expansion

Use this when the server's virtual disk has been enlarged (e.g. in VMware / Proxmox / VirtualBox) and you want to extend the root filesystem without rebooting.

### Check current state first

```bash
df -h /                # Current root filesystem size
sudo vgs               # Free space in volume group (look for VFree)
sudo pvs               # Physical volumes
```

### Step 1 — Resize the physical volume

After enlarging the virtual disk in your hypervisor:

```bash
sudo pvresize /dev/sda
```

### Step 2 — Extend the logical volume

```bash
sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
```

### Step 3 — Grow the filesystem

For ext4:

```bash
sudo resize2fs /dev/ubuntu-vg/ubuntu-lv
```

For XFS:

```bash
sudo xfs_growfs /
```

### Verify

```bash
df -h /
# Root filesystem should now show the larger size
```

> **Note:** `update-server.sh` runs these steps automatically via `_expand_lvm()` every time you run a server update. You only need to do this manually if you want to expand without running an update.

---

## 5. Checking Disk Space

### Overview of all mounts

```bash
df -h
```

### Root disk usage breakdown

```bash
du -sh /var/www/ARMGUARD_RDS_V1/       # App + venv + static
du -sh /var/backups/armguard/           # Local backups
du -sh /var/log/armguard/               # App logs
```

### External drive usage

```bash
df -h /mnt/backup
du -sh /mnt/backup/armguard/
ls -lht /mnt/backup/armguard/           # List backup sets by date
```

### Find largest directories under a path

```bash
sudo du -sh /var/backups/armguard/* | sort -h
```

---

## 6. Transferring Data to Another Server via External Drive

Use this method when network transfer is not available or when you want a physical offline copy.

### On the source server — run a final backup and unmount

```bash
# Run one final backup to make sure the drive is up to date
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh

# Safely unmount before physically removing
sudo umount /mnt/backup
```

### Physically move the drive to the target server

Plug the external drive into the target server.

### On the target server — identify and mount the drive

```bash
# Find the drive by its UUID or label
lsblk -o NAME,UUID,FSTYPE,LABEL,SIZE
sudo blkid | grep RDSDRIVEL    # or grep ff28a2b1

# Create mount point and mount
sudo mkdir -p /mnt/backup
sudo mount UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup

# Verify
ls /mnt/backup/armguard/
```

### Restore from the drive

Get the restore script (either from the drive itself or from GitHub):

```bash
# Option A — clone from GitHub
sudo git clone https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git /tmp/ARMGUARD_RDS_V1

# Option B — copy directly from the drive (if deploy.sh synced it there)
sudo cp /mnt/backup/armguard/transfer-to-server.sh /tmp/
```

Run restore directly from the external drive backup — no network needed:

```bash
sudo bash /tmp/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --restore-only \
    --backup /mnt/backup/armguard/20260504_020000
```

Replace `20260504_020000` with the backup timestamp you want to restore. To list available sets:

```bash
ls -lht /mnt/backup/armguard/
```

### After restore — unmount the drive

```bash
sudo umount /mnt/backup
```

### Return the drive to the original server and resume backups

**Step 1 — Plug the drive back into the original server.**

**Step 2 — Mount it:**

```bash
sudo mount UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup
mountpoint -q /mnt/backup && echo "MOUNTED" || echo "NOT MOUNTED"
```

**Step 3 — Verify the existing backups are intact:**

```bash
ls -lht /mnt/backup/armguard/
# Confirm your backup sets are still there
```

**Step 4 — Run a fresh backup to sync any data created while the drive was away:**

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh
```

This will create a new timestamped backup set and rsync it to the drive. Old sets are rotated automatically per the retention policy (default 7 days).

**Step 5 — Confirm the new backup landed on the drive:**

```bash
ls -lht /mnt/backup/armguard/
df -h /mnt/backup
```

**Step 6 — Verify future cron backups will still write to it:**

```bash
# The cron runs backup.sh every 3 hours as root.
# It checks mountpoint -q /mnt/backup before writing — no config change needed.
sudo crontab -l | grep backup.sh
```

The drive is now back in service as the external backup. No configuration changes are required — `backup.sh` auto-detects the mount at runtime on every run.

---

## 7. Replacing the External Drive

If you swap the external drive for a larger one:

1. **Unmount the old drive:**
   ```bash
   sudo umount /mnt/backup
   ```

2. **Physically swap the drive.**

3. **Identify the new drive:**
   ```bash
   lsblk -o NAME,UUID,FSTYPE,LABEL,SIZE
   ```

4. **Format if needed** (see [Section 2, Step 2](#step-2--format-the-drive-only-if-blank--new-drive)).

5. **Get the new UUID:**
   ```bash
   sudo blkid -o value -s UUID /dev/sdb3
   ```

6. **Update fstab** — replace the old UUID with the new one:
   ```bash
   sudo cp /etc/fstab /etc/fstab.bak.$(date +%Y%m%d)
   sudo nano /etc/fstab
   # Replace: UUID=old-uuid ...
   # With:    UUID=new-uuid /mnt/backup ext4 defaults,nofail,noatime 0 2
   ```

7. **Mount and verify:**
   ```bash
   sudo mount -a
   mountpoint -q /mnt/backup && echo "OK" || echo "FAILED"
   ```

8. **Restore previous backups** from the old drive (if needed):
   ```bash
   sudo rsync -av /path/to/old/backup/armguard/ /mnt/backup/armguard/
   ```

---

## 8. Troubleshooting

### External drive not mounting at boot

```bash
# Check fstab entry
cat /etc/fstab | grep backup

# Test fstab manually
sudo mount -a
dmesg | tail -20          # Check for mount errors

# Verify drive is detected
lsblk
sudo blkid
```

If the UUID changed (e.g. after reformatting), update fstab with the new UUID.

### "mount: /mnt/backup: can't read superblock"

The filesystem may be corrupted:

```bash
sudo fsck -f /dev/sdb3     # Run filesystem check (drive must be unmounted)
```

### Root filesystem is full

```bash
# Find what's consuming space
sudo du -sh /* 2>/dev/null | sort -h | tail -20

# Rotate old backups immediately
sudo find /var/backups/armguard -mindepth 1 -maxdepth 1 -type d -mtime +7 \
    -exec rm -rf {} \; -print

# Check log sizes
sudo du -sh /var/log/armguard/*
sudo truncate -s 0 /var/log/armguard/backup.log   # Clear log (only if very large)
```

### LVM: "No free space" after pvresize

The physical disk may not have actually grown. Check in your hypervisor that the virtual disk size was saved and the VM was restarted or the disk was hot-resized.

```bash
sudo fdisk -l /dev/sda    # Compare disk size vs partition table
sudo pvdisplay             # PV size vs actual disk
```

### "device is busy" when unmounting

```bash
sudo lsof /mnt/backup         # See which process is using it
# Kill the process or wait for backup to finish, then retry umount
sudo fuser -km /mnt/backup    # Force-kill all processes using the mount (use with caution)
sudo umount /mnt/backup
```

### Wrong permissions on /mnt/backup after reboot

```bash
sudo chmod 750 /mnt/backup
sudo mkdir -p /mnt/backup/armguard
```

---

## 9. Verifying Everything is Working

After any storage change, run these checks:

```bash
# 1. All mounts healthy
df -h

# 2. External drive mounted
mountpoint -q /mnt/backup && echo "External drive: MOUNTED" || echo "External drive: NOT MOUNTED"

# 3. Backup script dry-run (shows what would be written to external drive)
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh --dry-run

# 4. Run a real backup and verify it appears on external drive
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh
ls -lht /var/backups/armguard/
ls -lht /mnt/backup/armguard/
```
