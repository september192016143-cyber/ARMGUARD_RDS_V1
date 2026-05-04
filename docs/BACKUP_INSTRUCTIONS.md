# ArmGuard RDS V1 — Backup Instructions

**Server:** `192.168.0.162` · User: `rds` · App user: `armguard`  
**App path:** `/var/www/ARMGUARD_RDS_V1`  
**Backups:** `/var/backups/armguard/`

---

## Quick Reference

| Task | Command |
|------|---------|
| Run a backup now | `sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh` |
| Test without writing | `sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh --dry-run` |
| Run DB backup only | `sudo bash /var/www/ARMGUARD_RDS_V1/scripts/db-backup-cron.sh` |
| Inspect a backup | `sudo bash /var/www/ARMGUARD_RDS_V1/scripts/retrieve-backup.sh` |
| Transfer to another server | `sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh --target rds@IP` |
| List available backups | `ls -lht /var/backups/armguard/` |
| Check backup logs | `tail -50 /var/log/armguard/backup.log` |
| Verify a checksum | `cd /var/backups/armguard/TIMESTAMP && sha256sum -c *.sha256` |

---

## 1. Running a Manual Backup

### Full backup (database + media + .env)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh
```

The backup is saved to `/var/backups/armguard/YYYYMMDD_HHMMSS/`.

### Dry run — see what would be backed up without writing any files

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh --dry-run
```

### Override retention (keep more days)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/backup.sh --keep 30
```

### Database backup only (no media, no .env)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/db-backup-cron.sh
```

---

## 2. Viewing Backup Logs

```bash
# Live tail
sudo tail -f /var/log/armguard/backup.log

# Last 50 lines
sudo tail -50 /var/log/armguard/backup.log

# Filter errors only
sudo grep -i "error\|fail\|warn" /var/log/armguard/backup.log
```

---

## 3. Listing & Verifying Backups

### List all backup sets

```bash
ls -lht /var/backups/armguard/
```

### Show contents of the most recent backup

```bash
ls -lh /var/backups/armguard/$(ls -t /var/backups/armguard/ | head -1)/
```

### Verify a backup's SHA-256 checksum

```bash
cd /var/backups/armguard/20260504_020000
sha256sum -c armguard_backup_20260504_020001.sql.gz.sha256
# Expected output:
# armguard_backup_20260504_020001.sql.gz: OK
```

### Check total backup disk usage

```bash
du -sh /var/backups/armguard/
df -h /var/backups/armguard/
```

---

## 4. Inspecting a Backup (Read-Only)

Use `retrieve-backup.sh` to look inside a backup **without touching the live database**.

### Interactive mode (opens psql connected to a temp copy of the backup)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/retrieve-backup.sh
```

A numbered menu appears — select a backup. You get a `psql` prompt connected to a temporary database. The live `armguard` database is **never modified**. The temp database is dropped automatically when you type `\q`.

### Skip the menu — use a specific backup

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/retrieve-backup.sh \
    --backup /var/backups/armguard/20260504_020000
```

### Run a one-shot query and exit

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/retrieve-backup.sh \
    --query "SELECT * FROM personnel_personnel LIMIT 10"
```

### Export query results to CSV

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/retrieve-backup.sh \
    --query "SELECT item_id, model, serial_number, item_status FROM inventory_pistol" \
    --export /tmp/pistols_export.csv
```

### Useful queries inside the backup

```sql
\dt                                          -- list all tables
SELECT * FROM personnel_personnel LIMIT 10;
SELECT item_id, model, serial_number, item_status FROM inventory_pistol;
SELECT item_id, model, serial_number, item_status FROM inventory_rifle;
SELECT * FROM transactions_transactionlogs WHERE log_status = 'Open';
SELECT * FROM users_auditlog ORDER BY timestamp DESC LIMIT 20;
\q                                           -- exit (temp DB auto-dropped)
```

---

## 5. Transferring a Backup to Another Server

Use `transfer-to-server.sh` to copy a backup and restore it on another server.

### Transfer and restore in one step

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --target rds@192.168.0.200
```

A menu lets you pick which backup to transfer. The script will:
1. Copy files to the target via rsync
2. SSH into the target and run the full restore

### Transfer a specific backup (skip menu)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --target rds@192.168.0.200 \
    --backup /var/backups/armguard/20260504_020000
```

### Transfer files only — restore later

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --target rds@192.168.0.200 \
    --transfer-only
```

Then SSH to the target when ready:

```bash
ssh rds@192.168.0.200
sudo bash /tmp/transfer-to-server.sh \
    --restore-only \
    --backup /var/backups/armguard/20260504_020000
```

### Skip .env restore (target already has its own .env)

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --target rds@192.168.0.200 \
    --skip-env
```

### Use a custom SSH port or key

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --target rds@192.168.0.200 \
    --port 2222 \
    --key /root/.ssh/id_rsa_armguard
```

### After transfer — verify the target is running

```bash
ssh rds@192.168.0.200 "sudo systemctl status armguard-gunicorn"
ssh rds@192.168.0.200 "curl -sk https://localhost/ | head -5"
```

---

## 6. Restoring a Backup on the Same Server

> Use this to roll back the live server to a previous backup.

**Warning:** This drops and recreates the `armguard` database. All data since the backup will be lost.

```bash
sudo bash /var/www/ARMGUARD_RDS_V1/scripts/transfer-to-server.sh \
    --restore-only \
    --backup /var/backups/armguard/20260504_020000
```

This runs the full restore locally — no SSH or transfer needed.

---

## 7. Cron Jobs — Checking & Managing

### Check that backup crons are installed

```bash
sudo crontab -l                # root crons (backup.sh, renew-ssl-cert.sh)
crontab -u armguard -l         # armguard crons (db-backup-cron.sh)
```

Expected output for root crontab:

```
0 */3 * * * nice -n 19 ionice -c 3 /var/www/ARMGUARD_RDS_V1/scripts/backup.sh >> /var/log/armguard/backup.log 2>&1
0 3 1 * * /var/www/ARMGUARD_RDS_V1/scripts/renew-ssl-cert.sh >> /var/log/armguard/ssl-renewal.log 2>&1
0 3 * * * /var/www/ARMGUARD_RDS_V1/scripts/purge_camera_uploads >> /var/log/armguard/purge.log 2>&1
```

Expected output for armguard crontab:

```
0 2 * * * /var/www/ARMGUARD_RDS_V1/scripts/db-backup-cron.sh >> /var/log/armguard/backup.log 2>&1
```

### Reinstall backup crons (if missing)

```bash
# armguard daily DB backup
(crontab -u armguard -l 2>/dev/null | grep -v 'db-backup-cron'; \
 echo '0 2 * * * /var/www/ARMGUARD_RDS_V1/scripts/db-backup-cron.sh >> /var/log/armguard/backup.log 2>&1') \
 | crontab -u armguard -

# root full backup every 3 hours
(sudo crontab -l 2>/dev/null | grep -v 'backup.sh'; \
 echo '0 */3 * * * nice -n 19 ionice -c 3 /var/www/ARMGUARD_RDS_V1/scripts/backup.sh >> /var/log/armguard/backup.log 2>&1') \
 | sudo crontab -
```

---

## 8. External Drive

### Check if external drive is mounted

```bash
mountpoint -q /mnt/backup && echo "MOUNTED" || echo "NOT MOUNTED"
df -h /mnt/backup
```

### Mount the external drive manually

```bash
sudo mount /dev/sdb3 /mnt/backup
```

### Set up auto-mount (add to /etc/fstab if not already present)

```bash
echo "UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup ext4 defaults,nofail 0 2" \
    | sudo tee -a /etc/fstab
sudo mount -a
```

### List backups on external drive

```bash
ls -lht /mnt/backup/armguard/
```

---

## 9. Troubleshooting

### Backup script fails with "pg_dump not found"

```bash
sudo apt install -y postgresql-client
which pg_dump   # should print /usr/bin/pg_dump
```

### "Permission denied" on scripts

```bash
sudo chmod +x /var/www/ARMGUARD_RDS_V1/scripts/*.sh
```

### DB backup fails with "role does not exist"

The `armguard` PostgreSQL role may be missing:

```bash
sudo -u postgres psql -c "CREATE USER armguard WITH PASSWORD 'yourpassword' CREATEDB;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE armguard TO armguard;"
```

### retrieve-backup.sh fails to drop temp database

If the script crashes before cleanup, drop it manually:

```bash
sudo -u postgres psql -c "DROP DATABASE IF EXISTS armguard_retrieve_20260504_020000;"
# Or list all temp DBs:
sudo -u postgres psql -c "\l" | grep armguard_retrieve
```

### Transfer fails — SSH connection refused

```bash
# Test SSH first
ssh -p 22 rds@192.168.0.200 "echo OK"

# Try with verbose output for diagnosis
ssh -v -p 22 rds@192.168.0.200 "echo OK"
```

### Backup log is full of "DRY-RUN" messages

The cron is calling `backup.sh --dry-run`. Edit crontab to remove `--dry-run`:

```bash
sudo crontab -e
```

### Check if gunicorn restarted after restore

```bash
sudo systemctl status armguard-gunicorn
sudo journalctl -u armguard-gunicorn -n 30 --no-pager
```

---

## 10. After a Restore — Checklist

After restoring on a new or same server, verify:

- [ ] `.env` is correct for this server — update `ALLOWED_HOSTS`, `DB_HOST`, `SECRET_KEY`
- [ ] Gunicorn is running: `sudo systemctl status armguard-gunicorn`
- [ ] Nginx is running: `sudo systemctl status nginx`
- [ ] App responds: `curl -sk https://localhost/ | head -5`
- [ ] Superuser exists (create if new server):
  ```bash
  sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
      /var/www/ARMGUARD_RDS_V1/project/manage.py createsuperuser
  ```
- [ ] Media files are accessible (images load in the UI)
- [ ] No pending migrations:
  ```bash
  sudo -u armguard /var/www/ARMGUARD_RDS_V1/venv/bin/python \
      /var/www/ARMGUARD_RDS_V1/project/manage.py showmigrations | grep "\[ \]"
  ```
