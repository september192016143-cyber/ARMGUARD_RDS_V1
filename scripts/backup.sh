#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Consolidated Backup Script
# =============================================================================
# Backs up:
#   1. SQLite database (hot-copy via Django management command)
#   2. media/ directory (user-uploaded files)
#   3. .env file (encrypted or plaintext)
#
# Output: /var/backups/armguard/YYYYMMDD_HHMMSS/
# Retention: 7 days (configurable via KEEP_DAYS)
# Optional: GPG encryption of all output (set ARMGUARD_BACKUP_GPG_RECIPIENT in .env)
#
# Cron installation (runs daily at 02:00 as root):
#   0 2 * * * /var/www/ARMGUARD_RDS_V1/scripts/backup.sh >> /var/log/armguard/backup.log 2>&1
#
# Usage:
#   sudo bash scripts/backup.sh [--dry-run] [--keep N]
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEPLOY_USER="armguard"
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
PROJECT_DIR="$DEPLOY_DIR/project"
VENV_PYTHON="$DEPLOY_DIR/venv/bin/python"
ENV_FILE="$DEPLOY_DIR/.env"
BACKUP_ROOT="/var/backups/armguard"
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

DB_FILE="$PROJECT_DIR/db.sqlite3"

if [[ ! -f "$DB_FILE" ]]; then
    warn "db.sqlite3 not found at $DB_FILE — skipping database backup."
else
    if [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$BACKUP_DIR"
        DB_BACKUP="$BACKUP_DIR/db_${TIMESTAMP}.sqlite3"

        # Use Django's sqlite3.Connection.backup() for a consistent hot-copy.
        # Falls back to cp if the management command is unavailable.
        if sudo -u "$DEPLOY_USER" bash -c "
            export DJANGO_SETTINGS_MODULE=armguard.settings.production
            [[ -f '$ENV_FILE' ]] && set -a && source <(grep -v '^\s*#' '$ENV_FILE' | grep -E '^\s*\w+=') && set +a || true
            cd '$PROJECT_DIR'
            '$VENV_PYTHON' manage.py db_backup --output '$BACKUP_DIR' --keep 9999 2>&1
        " >> /var/log/armguard/backup.log 2>&1; then
            ok "Database backed up via Django management command."
            # Rename to standard name if db_backup created a differently-named file
            LATEST_DB=$(find "$BACKUP_DIR" -name "*.sqlite3" | sort | tail -1)
            [[ "$LATEST_DB" != "$DB_BACKUP" && -f "$LATEST_DB" ]] && mv "$LATEST_DB" "$DB_BACKUP" || true
        else
            warn "Django db_backup unavailable — falling back to cp snapshot."
            cp "$DB_FILE" "$DB_BACKUP"
        fi
        ok "Database: $DB_BACKUP ($(du -sh "$DB_BACKUP" | awk '{print $1}'))"
    else
        log "[DRY-RUN] Would backup: $DB_FILE → $BACKUP_DIR/db_${TIMESTAMP}.sqlite3"
    fi
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
    ok "Backup complete: $BACKUP_DIR"
    log "Backup store: $BACKUP_ROOT ($BACKUP_COUNT set(s), $TOTAL_SIZE total)"
fi
