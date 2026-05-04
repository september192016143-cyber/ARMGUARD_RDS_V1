#!/usr/bin/env bash
# =============================================================================
# ARMGUARD RDS V1 — Database Backup Cron Wrapper
# =============================================================================
# This script is called by cron to perform a daily SQLite hot-copy backup.
# It invokes the Django management command 'db_backup' which uses
# sqlite3.Connection.backup() for a safe, consistent snapshot.
#
# Cron installation (as root or via crontab -u armguard -e):
#   0 2 * * * /var/www/ARMGUARD_RDS_V1/scripts/db-backup-cron.sh >> /var/log/armguard/backup.log 2>&1
#
# Configuration:
#   Edit the variables below to match your deployment.
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
BACKUP_DIR="$DEPLOY_DIR/backups"
KEEP_DAYS=14          # Number of daily backups to retain
LOG_PREFIX="[BACKUP]"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
log() { echo "$TIMESTAMP $LOG_PREFIX $*"; }
err() { echo "$TIMESTAMP $LOG_PREFIX ERROR: $*" >&2; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
[[ -f "$VENV_PYTHON" ]] || { err "Python venv not found at $VENV_PYTHON"; exit 1; }
[[ -d "$PROJECT_DIR" ]] || { err "Project dir not found: $PROJECT_DIR"; exit 1; }

mkdir -p "$BACKUP_DIR"

# ---------------------------------------------------------------------------
# Run Django db_backup management command
# ---------------------------------------------------------------------------
log "Starting database backup (keep=$KEEP_DAYS days)..."

# Load env vars for the Django management command
ENV_ARGS=""
if [[ -f "$ENV_FILE" ]]; then
    # Export only KEY=VALUE lines (no comments, no blank lines)
    set -a
    # shellcheck source=/dev/null
    source <(grep -v '^\s*#' "$ENV_FILE" | grep -E '^\s*\w+=')
    set +a
fi

export DJANGO_SETTINGS_MODULE=armguard.settings.production

# This script runs as the armguard user (via crontab -u armguard).
# Do NOT use sudo here — armguard does not have sudo privileges.
RESULT=$(cd "$PROJECT_DIR" && \
    "$VENV_PYTHON" manage.py db_backup --output "$BACKUP_DIR" --keep "$KEEP_DAYS" 2>&1 \
    || echo "COMMAND_FAILED")

if echo "$RESULT" | grep -q "COMMAND_FAILED\|Error\|Traceback"; then
    err "db_backup command reported an error:"
    err "$RESULT"
    exit 1
fi

log "db_backup output: $RESULT"

# ---------------------------------------------------------------------------
# Report backup directory size
# ---------------------------------------------------------------------------
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "*.sqlite3" -o -name "*.db" 2>/dev/null | wc -l)
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}' || echo "unknown")
log "Backup directory: $BACKUP_DIR ($BACKUP_COUNT files, $BACKUP_SIZE total)"

# ---------------------------------------------------------------------------
# Optional GPG encryption
# Set ARMGUARD_BACKUP_GPG_RECIPIENT in .env to enable, e.g.:
#   ARMGUARD_BACKUP_GPG_RECIPIENT=backup@example.com
# The plaintext .sqlite3 file is securely shredded after encryption.
# ---------------------------------------------------------------------------
if [[ -n "${ARMGUARD_BACKUP_GPG_RECIPIENT:-}" ]]; then
    LATEST_BACKUP=$(find "$BACKUP_DIR" -name "armguard_backup_*.sqlite3" | sort | tail -1)
    if [[ -f "$LATEST_BACKUP" ]]; then
        if command -v gpg &>/dev/null; then
            log "GPG-encrypting backup for recipient: $ARMGUARD_BACKUP_GPG_RECIPIENT"
            gpg --batch --yes \
                --recipient "$ARMGUARD_BACKUP_GPG_RECIPIENT" \
                --output "${LATEST_BACKUP}.gpg" \
                --encrypt "$LATEST_BACKUP" \
            && shred -u "$LATEST_BACKUP" \
            && log "Encrypted: ${LATEST_BACKUP}.gpg (plaintext removed)" \
            || err "GPG encryption failed — plaintext backup retained at $LATEST_BACKUP"
        else
            err "GPG encryption requested but 'gpg' is not installed — skipping encryption"
        fi
    fi
fi

log "Backup complete."
