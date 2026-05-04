#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Consolidated Backup Script
# =============================================================================
# Backs up:
#   1. SQLite database (hot-copy via Django management command)
#   2. media/ directory (user-uploaded files)
#   3. .env file (encrypted or plaintext)
#
# Output (local)  : /var/backups/armguard/YYYYMMDD_HHMMSS/
# Output (external): /mnt/backup/armguard/YYYYMMDD_HHMMSS/  (if drive mounted)
# Retention: 7 days (configurable via KEEP_DAYS)
# Optional: GPG encryption of all output (set ARMGUARD_BACKUP_GPG_RECIPIENT in .env)
#
# External drive setup:
#   UUID="ff28a2b1-df2f-402b-9b88-38133225a40f" (RDSDRIVEL — /dev/sdb3, 672G)
#   Mount:   sudo mount /dev/sdb3 /mnt/backup
#   fstab:   UUID=ff28a2b1-df2f-402b-9b88-38133225a40f /mnt/backup ext4 defaults,nofail 0 2
#   Check:   mountpoint -q /mnt/backup && echo mounted || echo not mounted
#
# Cron installation (runs every 3 hours as root — low-priority, background-safe):
#   0 */3 * * * nice -n 19 ionice -c 3 /var/www/ARMGUARD_RDS_V1/scripts/backup.sh >> /var/log/armguard/backup.log 2>&1
#
# Install/update cron entry (run once on the server):
#   (crontab -l 2>/dev/null | grep -v 'backup.sh'; echo '0 */3 * * * nice -n 19 ionice -c 3 /var/www/ARMGUARD_RDS_V1/scripts/backup.sh >> /var/log/armguard/backup.log 2>&1') | crontab -
#
# Runs at: 00:00 03:00 06:00 09:00 12:00 15:00 18:00 21:00
# nice -n 19   → lowest CPU scheduling priority (web workers stay at 0)
# ionice -c 3  → idle I/O class (disk reads/writes only when system is idle)
#
# Usage:
#   sudo bash scripts/backup.sh [--dry-run] [--keep N]
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Self-limit CPU and I/O priority so backups never stall the web process.
# These are no-ops if the tools are unavailable (non-fatal).
# ---------------------------------------------------------------------------
renice -n 19 $$ &>/dev/null || true
if command -v ionice &>/dev/null; then
    ionice -c 3 -p $$ &>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEPLOY_USER="armguard"
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
PROJECT_DIR="$DEPLOY_DIR/project"
VENV_PYTHON="$DEPLOY_DIR/venv/bin/python"
ENV_FILE="$DEPLOY_DIR/.env"
BACKUP_ROOT="/var/backups/armguard"
EXTERNAL_BACKUP_MOUNT="/mnt/backup"
EXTERNAL_BACKUP_DIR="$EXTERNAL_BACKUP_MOUNT/armguard"
KEEP_DAYS=7
DRY_RUN=false
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

# ---------------------------------------------------------------------------
# Colour / logging helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[BACKUP $(date '+%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --keep)    KEEP_DAYS="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: sudo $0 [--dry-run] [--keep N]"
            echo "  --dry-run  Show what would be backed up without writing"
            echo "  --keep N   Keep N days of backups (default: $KEEP_DAYS)"
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root: sudo $0"
[[ -f "$VENV_PYTHON" ]] || die "Python venv not found at $VENV_PYTHON"
[[ -d "$PROJECT_DIR" ]] || die "Project dir not found: $PROJECT_DIR"

# Ensure backup root exists with tight permissions (0700 — root-only read/write).
# This protects the plaintext .env copy (contains DJANGO_SECRET_KEY) when GPG
# encryption is not configured.
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

TIMESTAMP_DISPLAY="$(date '+%Y-%m-%d %H:%M:%S')"
echo
echo -e "${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         ArmGuard RDS V1 — Backup                          ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
log "Timestamp : $TIMESTAMP_DISPLAY"
log "Backup dir: $BACKUP_DIR"
log "Retention : $KEEP_DAYS days"
[[ "$DRY_RUN" == "true" ]] && warn "DRY-RUN MODE — nothing will be written"

# Load .env for GPG recipient and other settings
# Security warning: if GPG encryption is not configured the .env backup (which
# contains DJANGO_SECRET_KEY) will be stored as plaintext. The backup root is
# chmod 700 so root-only access applies, but enabling GPG is strongly recommended.
# Set ARMGUARD_BACKUP_GPG_RECIPIENT=<key-id> in .env to encrypt all output.
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    source <(grep -v '^\s*#' "$ENV_FILE" | grep -E '^\s*\w+=') 2>/dev/null || true
    set +a
fi

# ---------------------------------------------------------------------------
# 1. SQLite database backup (via Django management command for consistent snapshot)
# ---------------------------------------------------------------------------
log "─── Step 1/3: Database backup ───────────────────────────────────"

if [[ "$DRY_RUN" == "false" ]]; then
    mkdir -p "$BACKUP_DIR"

    DB_FILE="$PROJECT_DIR/db.sqlite3"

    if sudo -u "$DEPLOY_USER" bash -c "
        export DJANGO_SETTINGS_MODULE=armguard.settings.production
        [[ -f '$ENV_FILE' ]] && set -a && source <(grep -v '^\s*#' '$ENV_FILE' | grep -E '^\s*\w+=') && set +a || true
        cd '$PROJECT_DIR'
        '$VENV_PYTHON' manage.py db_backup --output '$BACKUP_DIR' --keep 9999 2>&1
    " >> /var/log/armguard/backup.log 2>&1; then
        ok "Database backed up via Django management command."
        LATEST_DB=$(find "$BACKUP_DIR" -name "*.sqlite3" -o -name "*.sql.gz" 2>/dev/null | sort | tail -1)
        [[ -n "$LATEST_DB" ]] && ok "  → $LATEST_DB" || true
    else
        warn "Django db_backup failed — check /var/log/armguard/backup.log for details."
        # SQLite fallback only (no fallback for PostgreSQL — pg_dump must be available)
        if [[ -f "$DB_FILE" ]]; then
            warn "Falling back to cp snapshot of SQLite db."
            cp "$DB_FILE" "$BACKUP_DIR/db_${TIMESTAMP}.sqlite3"
            ok "Database (fallback): $BACKUP_DIR/db_${TIMESTAMP}.sqlite3"
        fi
    fi
else
    log "[DRY-RUN] Would run: manage.py db_backup --output $BACKUP_DIR"
fi

# ---------------------------------------------------------------------------
# 2. Media directory backup (user-uploaded files)
# ---------------------------------------------------------------------------
log "─── Step 2/3: Media backup ──────────────────────────────────────"

MEDIA_DIR="$PROJECT_DIR/media"

if [[ ! -d "$MEDIA_DIR" ]] || [[ -z "$(ls -A "$MEDIA_DIR" 2>/dev/null)" ]]; then
    warn "media/ is empty or missing — skipping media backup."
else
    if [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$BACKUP_DIR"
        MEDIA_ARCHIVE="$BACKUP_DIR/media_${TIMESTAMP}.tar.gz"
        tar -czf "$MEDIA_ARCHIVE" -C "$PROJECT_DIR" media/
        ok "Media: $MEDIA_ARCHIVE ($(du -sh "$MEDIA_ARCHIVE" | awk '{print $1}'))"
    else
        MEDIA_SIZE=$(du -sh "$MEDIA_DIR" 2>/dev/null | awk '{print $1}' || echo "?")
        log "[DRY-RUN] Would archive: $MEDIA_DIR ($MEDIA_SIZE) → $BACKUP_DIR/media_${TIMESTAMP}.tar.gz"
    fi
fi

# ---------------------------------------------------------------------------
# 3. .env file backup (credentials — keep encrypted or tightly permissioned)
# ---------------------------------------------------------------------------
log "─── Step 3/3: .env backup ───────────────────────────────────────"

if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found at $ENV_FILE — skipping."
else
    if [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$BACKUP_DIR"
        ENV_BACKUP="$BACKUP_DIR/env_${TIMESTAMP}.env"
        cp "$ENV_FILE" "$ENV_BACKUP"
        chmod 600 "$ENV_BACKUP"
        ok ".env: $ENV_BACKUP"
    else
        log "[DRY-RUN] Would copy: $ENV_FILE → $BACKUP_DIR/env_${TIMESTAMP}.env"
    fi
fi

# ---------------------------------------------------------------------------
# Optional: GPG encryption of the entire backup directory
# Set ARMGUARD_BACKUP_GPG_RECIPIENT in .env to enable.
# The plaintext files are shredded after encryption.
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "false" && -z "${ARMGUARD_BACKUP_GPG_RECIPIENT:-}" ]]; then
    warn "GPG encryption is NOT configured — backup directory contains plaintext secrets."
    warn "Set ARMGUARD_BACKUP_GPG_RECIPIENT=<key-id> in .env to encrypt backups."
    warn "Backup root is chmod 700 (root-only), but encryption is strongly recommended."
fi

if [[ "$DRY_RUN" == "false" && -n "${ARMGUARD_BACKUP_GPG_RECIPIENT:-}" ]]; then
    log "GPG-encrypting backup for: $ARMGUARD_BACKUP_GPG_RECIPIENT"
    if ! command -v gpg &>/dev/null; then
        warn "'gpg' not installed — skipping encryption. Install with: apt install gnupg"
    else
        ARCHIVE_BASE="$BACKUP_ROOT/armguard_backup_${TIMESTAMP}"
        tar -czf "${ARCHIVE_BASE}.tar.gz" -C "$BACKUP_ROOT" "$TIMESTAMP/"
        gpg --batch --yes \
            --recipient "$ARMGUARD_BACKUP_GPG_RECIPIENT" \
            --output "${ARCHIVE_BASE}.tar.gz.gpg" \
            --encrypt "${ARCHIVE_BASE}.tar.gz" \
        && shred -u "${ARCHIVE_BASE}.tar.gz" \
        && rm -rf "$BACKUP_DIR" \
        && ok "Encrypted: ${ARCHIVE_BASE}.tar.gz.gpg (plaintext removed)" \
        || warn "GPG encryption failed — plaintext backup retained at $BACKUP_DIR"
    fi
fi

# ---------------------------------------------------------------------------
# Sync to external drive (if mounted at EXTERNAL_BACKUP_MOUNT)
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "false" ]]; then
    if mountpoint -q "$EXTERNAL_BACKUP_MOUNT" 2>/dev/null; then
        log "─── External drive backup ($EXTERNAL_BACKUP_MOUNT) ──────────────────"
        mkdir -p "$EXTERNAL_BACKUP_DIR"
        if rsync -a --info=progress2 "$BACKUP_ROOT/$TIMESTAMP/" "$EXTERNAL_BACKUP_DIR/$TIMESTAMP/" 2>&1; then
            ok "Synced to external: $EXTERNAL_BACKUP_DIR/$TIMESTAMP"
            # Rotate old external backups
            EXT_DELETED=0
            while IFS= read -r old_ext; do
                rm -rf "$old_ext"
                EXT_DELETED=$(( EXT_DELETED + 1 ))
                log "  Deleted external: $old_ext"
            done < <(find "$EXTERNAL_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" 2>/dev/null)
            [[ "$EXT_DELETED" -gt 0 ]] && ok "Rotated $EXT_DELETED old external backup(s)." || log "No external backups to rotate."
        else
            warn "rsync to external drive failed — local backup retained at $BACKUP_ROOT/$TIMESTAMP"
        fi
    else
        warn "External drive not mounted at $EXTERNAL_BACKUP_MOUNT — skipping external backup."
        warn "Mount with: sudo mount /dev/sdb3 $EXTERNAL_BACKUP_MOUNT"
    fi
else
    if mountpoint -q "$EXTERNAL_BACKUP_MOUNT" 2>/dev/null; then
        log "[DRY-RUN] Would sync to external: $EXTERNAL_BACKUP_DIR/$TIMESTAMP"
    else
        log "[DRY-RUN] External drive not mounted at $EXTERNAL_BACKUP_MOUNT"
    fi
fi

# ---------------------------------------------------------------------------
# Rotate old backups
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "false" ]]; then
    log "─── Rotating backups older than $KEEP_DAYS days ─────────────────────"
    DELETED=0
    while IFS= read -r old_backup; do
        rm -rf "$old_backup"
        DELETED=$(( DELETED + 1 ))
        log "  Deleted: $old_backup"
    done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" 2>/dev/null)
    # Also rotate encrypted tarballs
    while IFS= read -r old_archive; do
        rm -f "$old_archive"
        DELETED=$(( DELETED + 1 ))
        log "  Deleted: $old_archive"
    done < <(find "$BACKUP_ROOT" -maxdepth 1 -name "*.tar.gz.gpg" -mtime "+${KEEP_DAYS}" 2>/dev/null)
    [[ "$DELETED" -gt 0 ]] && ok "Rotated $DELETED old backup(s)." || log "No backups to rotate."
else
    log "[DRY-RUN] Would rotate backups older than $KEEP_DAYS days in $BACKUP_ROOT"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "false" ]]; then
    TOTAL_SIZE=$(du -sh "$BACKUP_ROOT" 2>/dev/null | awk '{print $1}' || echo "unknown")
    BACKUP_COUNT=$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    echo
    ok "Backup complete : $BACKUP_DIR"
    log "Local store     : $BACKUP_ROOT ($BACKUP_COUNT set(s), $TOTAL_SIZE total)"
    if mountpoint -q "$EXTERNAL_BACKUP_MOUNT" 2>/dev/null; then
        EXT_SIZE=$(du -sh "$EXTERNAL_BACKUP_DIR" 2>/dev/null | awk '{print $1}' || echo "unknown")
        EXT_FREE=$(df -h "$EXTERNAL_BACKUP_MOUNT" 2>/dev/null | awk 'NR==2{print $4}' || echo "unknown")
        EXT_COUNT=$(find "$EXTERNAL_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
        log "External drive  : $EXTERNAL_BACKUP_DIR ($EXT_COUNT set(s), $EXT_SIZE used, $EXT_FREE free)"
    else
        warn "External drive not mounted — external copy was skipped."
    fi
fi
