#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Backup Transfer & Recovery Script
# =============================================================================
# Transfers a backup set from this server to a target server and restores it.
#
# Two modes:
#   --transfer-only   Copy the backup files to the target, do NOT restore yet.
#   --restore-only    The backup is already on the target; restore it in-place.
#                     (Run this directly on the target server, no SSH needed.)
#   (default)         Transfer AND restore in one pass.
#
# Usage (run on the SOURCE server):
#   sudo bash scripts/transfer-to-server.sh --target rds@192.168.0.200
#   sudo bash scripts/transfer-to-server.sh --target rds@192.168.0.200 --backup /var/backups/armguard/20260504_072232
#   sudo bash scripts/transfer-to-server.sh --target rds@192.168.0.200 --transfer-only
#   sudo bash scripts/transfer-to-server.sh --target rds@192.168.0.200 --skip-env
#
# Usage (run directly ON the target server for restore-only):
#   sudo bash scripts/transfer-to-server.sh --restore-only --backup /var/backups/armguard/20260504_072232
#
# What it does:
#   1. Selects a backup set (menu or --backup)
#   2. Verifies SHA-256 checksum if present
#   3. rsyncs backup files + this script to the target server
#   4. SSH-invokes itself on the target in --restore-only mode
#      a. Creates armguard user + PostgreSQL role if missing
#      b. Drops & recreates the 'armguard' database
#      c. Restores the pg_dump (.sql.gz)
#      d. Restores media/ files
#      e. Optionally copies .env
#      f. Restarts armguard-gunicorn if running
#
# Requirements (source):  rsync, ssh, gzip
# Requirements (target):  psql, pg_dump, rsync, python3 (for Django migrations check)
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Configuration (matches deploy.sh)
# ---------------------------------------------------------------------------
BACKUP_ROOT="/var/backups/armguard"
EXTERNAL_BACKUP_DIR="/mnt/backup/armguard"   # External HDD: sda3, UUID ff28a2b1-df2f-402b-9b88-38133225a40f
                                               # Root disk: nvme0n1 — device names can shift, always mount by UUID
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
ENV_FILE="$DEPLOY_DIR/.env"
PROJECT_DIR="$DEPLOY_DIR/project"
MEDIA_DIR="$PROJECT_DIR/media"
VENV_PYTHON="$DEPLOY_DIR/venv/bin/python"
SERVICE_NAME="armguard-gunicorn"
DEPLOY_USER="armguard"
REMOTE_BACKUP_STAGING="/var/backups/armguard"   # Where files land on target

# ---------------------------------------------------------------------------
# Colours / logging
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${CYAN}[TRANSFER $(date '+%H:%M:%S')]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}     $*"; }
err()     { echo -e "${RED}[ERROR]${NC}    $*" >&2; }
ok()      { echo -e "${GREEN}[OK]${NC}      $*"; }
step()    { echo; echo -e "${BOLD}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
die()     { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
TARGET=""
CHOSEN_BACKUP=""
TRANSFER_ONLY=false
RESTORE_ONLY=false
SKIP_ENV=false
SKIP_MEDIA=false
SSH_PORT=22
SSH_KEY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)        TARGET="$2";          shift 2 ;;
        --backup)        CHOSEN_BACKUP="$2";   shift 2 ;;
        --transfer-only) TRANSFER_ONLY=true;   shift ;;
        --restore-only)  RESTORE_ONLY=true;    shift ;;
        --skip-env)      SKIP_ENV=true;        shift ;;
        --skip-media)    SKIP_MEDIA=true;      shift ;;
        --port)          SSH_PORT="$2";        shift 2 ;;
        --key)           SSH_KEY="$2";         shift 2 ;;
        --help|-h)
            echo "Usage: sudo $0 [options]"
            echo
            echo "  --target USER@IP    Target server (required unless --restore-only)"
            echo "  --backup  DIR       Specific backup directory to use (skips menu)"
            echo "  --transfer-only     Copy files to target but do NOT restore"
            echo "  --restore-only      Skip transfer; restore backup already on this machine"
            echo "  --skip-env          Do not copy/restore .env file"
            echo "  --skip-media        Do not transfer/restore media/ files"
            echo "  --port    PORT      SSH port on target (default: 22)"
            echo "  --key     FILE      SSH private key for target"
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# Validate
if [[ "$RESTORE_ONLY" == "false" && -z "$TARGET" ]]; then
    die "Specify --target USER@IP  (or use --restore-only to restore without SSH)"
fi

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   ArmGuard RDS V1 — Backup Transfer & Recovery           ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
[[ "$RESTORE_ONLY"  == "true"  ]] && echo -e "  Mode: ${YELLOW}RESTORE-ONLY (running on target)${NC}"
[[ "$TRANSFER_ONLY" == "true"  ]] && echo -e "  Mode: ${YELLOW}TRANSFER-ONLY (no restore)${NC}"
[[ "$RESTORE_ONLY"  == "false" && "$TRANSFER_ONLY" == "false" ]] && \
    echo -e "  Mode: ${GREEN}TRANSFER + RESTORE${NC}"
[[ -n "$TARGET" ]] && echo -e "  Target: $TARGET"
echo

# ============================================================================
# RESTORE MODE — runs on the TARGET server
# ============================================================================
_do_restore() {
    local backup_dir="$1"

    [[ $EUID -eq 0 ]] || die "Run as root: sudo $0 --restore-only --backup $backup_dir"
    [[ -d "$backup_dir" ]]  || die "Backup directory not found: $backup_dir"
    command -v psql &>/dev/null || die "'psql' not found. Install: sudo apt install postgresql-client"

    # Locate dump file
    local dump_file sqlite_file
    dump_file=$(find "$backup_dir" -name "*.sql.gz"  2>/dev/null | sort | tail -1 || true)
    sqlite_file=$(find "$backup_dir" -name "*.sqlite3" 2>/dev/null | sort | tail -1 || true)
    local media_archive env_backup
    media_archive=$(find "$backup_dir" -name "media_*.tar.gz" 2>/dev/null | sort | tail -1 || true)
    env_backup=$(find "$backup_dir" -name "env_*.env" 2>/dev/null | sort | tail -1 || true)

    # Checksum verification
    local sha_file
    sha_file=$(find "$backup_dir" -name "*.sha256" 2>/dev/null | sort | tail -1 || true)
    if [[ -n "$sha_file" ]]; then
        log "Verifying backup integrity …"
        if (cd "$backup_dir" && sha256sum -c "$(basename "$sha_file")" --quiet 2>/dev/null); then
            ok "Checksum verified."
        else
            warn "Checksum MISMATCH. The backup may be incomplete or corrupted."
            read -rp "  Continue anyway? [yes/N]: " _cont
            [[ "${_cont,,}" == "yes" ]] || die "Aborted by user."
        fi
    else
        warn "No .sha256 sidecar — skipping integrity check."
    fi

    # ---------------------------------------------------------------------------
    step "1. Database restore"
    # ---------------------------------------------------------------------------
    if [[ -n "$dump_file" ]]; then
        log "Dump: $dump_file"

        # Load .env for DB credentials if available
        local db_name="armguard" db_user="armguard" db_host="127.0.0.1" db_port="5432" db_pass=""
        if [[ -f "$ENV_FILE" ]]; then
            set -a
            source <(grep -v '^\s*#' "$ENV_FILE" | grep -E '^\s*\w+=') 2>/dev/null || true
            set +a
            db_name="${DB_NAME:-armguard}"
            db_user="${DB_USER:-armguard}"
            db_host="${DB_HOST:-127.0.0.1}"
            db_port="${DB_PORT:-5432}"
            db_pass="${DB_PASSWORD:-}"
        fi

        export PGPASSWORD="$db_pass"
        # L-15: Ensure PGPASSWORD is unset even if an error causes early exit.
        trap 'unset PGPASSWORD' RETURN ERR

        # Ensure the armguard PostgreSQL role exists
        if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$db_user'" \
                | grep -q 1 2>/dev/null; then
            log "Creating PostgreSQL role '$db_user' …"
            sudo -u postgres psql -c \
                "CREATE USER $db_user WITH PASSWORD '$db_pass' CREATEDB;" 2>/dev/null \
                && ok "Role '$db_user' created." \
                || warn "Could not create role — it may already exist."
        fi

        # Stop the app before touching the DB
        if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            log "Stopping $SERVICE_NAME …"
            systemctl stop "$SERVICE_NAME"
            ok "$SERVICE_NAME stopped."
        fi

        # Drop and recreate
        log "Dropping existing database '$db_name' (if any) …"
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS $db_name;" 2>/dev/null || true
        log "Creating database '$db_name' …"
        sudo -u postgres psql -c "CREATE DATABASE $db_name OWNER $db_user;" \
            || die "Failed to create database '$db_name'."

        log "Restoring from $dump_file …"
        if gunzip -c "$dump_file" | sudo -u postgres psql "$db_name" > /dev/null 2>&1; then
            ok "Database restored: $db_name"
        else
            warn "Restore completed with warnings (may be harmless role/extension notices)."
        fi

        unset PGPASSWORD

    elif [[ -n "$sqlite_file" ]]; then
        log "This backup contains a SQLite database — restoring …"

        # Stop the app before touching the database file
        if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            log "Stopping $SERVICE_NAME …"
            systemctl stop "$SERVICE_NAME"
            ok "$SERVICE_NAME stopped."
        fi

        # Remove any orphaned WAL/SHM files that would corrupt the restored DB
        rm -f "$PROJECT_DIR/db.sqlite3" \
              "$PROJECT_DIR/db.sqlite3-wal" \
              "$PROJECT_DIR/db.sqlite3-shm"

        # Copy the backed-up database into place
        mkdir -p "$PROJECT_DIR"
        cp "$sqlite_file" "$PROJECT_DIR/db.sqlite3"
        chown "$DEPLOY_USER:$DEPLOY_USER" "$PROJECT_DIR/db.sqlite3"
        chmod 640 "$PROJECT_DIR/db.sqlite3"
        ok "SQLite database restored → $PROJECT_DIR/db.sqlite3"
    else
        warn "No database dump found in $backup_dir — skipping database restore."
    fi

    # ---------------------------------------------------------------------------
    step "2. Media files restore"
    # ---------------------------------------------------------------------------
    if [[ "$SKIP_MEDIA" == "true" ]]; then
        log "Skipping media restore (--skip-media)."
    elif [[ -n "$media_archive" ]]; then
        log "Media archive: $media_archive"
        mkdir -p "$PROJECT_DIR"
        # Backup existing media before overwriting
        if [[ -d "$MEDIA_DIR" ]]; then
            local media_bak="/var/backups/armguard/media_pre_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
            log "Backing up existing media → $media_bak"
            tar -czf "$media_bak" -C "$PROJECT_DIR" media/ 2>/dev/null || true
            ok "Existing media backed up to $media_bak"
        fi
        tar -xzf "$media_archive" -C "$PROJECT_DIR"
        chown -R "$DEPLOY_USER:$DEPLOY_USER" "$MEDIA_DIR" 2>/dev/null || true
        ok "Media restored to $MEDIA_DIR"
    else
        warn "No media archive found in $backup_dir — skipping media restore."
    fi

    # ---------------------------------------------------------------------------
    step "3. .env restore"
    # ---------------------------------------------------------------------------
    if [[ "$SKIP_ENV" == "true" ]]; then
        log "Skipping .env restore (--skip-env)."
    elif [[ -n "$env_backup" ]]; then
        if [[ -f "$ENV_FILE" ]]; then
            local env_bak="$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
            cp "$ENV_FILE" "$env_bak"
            log "Existing .env backed up to $env_bak"
        fi
        cp "$env_backup" "$ENV_FILE"
        chmod 640 "$ENV_FILE"
        chown "root:$DEPLOY_USER" "$ENV_FILE" 2>/dev/null || true
        ok ".env restored."
        warn "IMPORTANT: Review $ENV_FILE — update DB host, secret key, ALLOWED_HOSTS for this server."
    else
        warn "No .env backup found — skipping. You must configure $ENV_FILE manually."
    fi

    # ---------------------------------------------------------------------------
    step "4. Fix ownership & permissions"
    # ---------------------------------------------------------------------------
    if [[ -d "$DEPLOY_DIR" ]]; then
        chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR" 2>/dev/null || true
        chown "root:$DEPLOY_USER" "$ENV_FILE" 2>/dev/null || true
        chmod 640 "$ENV_FILE" 2>/dev/null || true
        ok "Ownership fixed: $DEPLOY_DIR → $DEPLOY_USER:$DEPLOY_USER"
    fi

    # ---------------------------------------------------------------------------
    step "5. Run Django migrations (safety check)"
    # ---------------------------------------------------------------------------
    if [[ -f "$VENV_PYTHON" ]]; then
        log "Checking for unapplied migrations …"
        local migrate_out
        migrate_out=$(sudo -u "$DEPLOY_USER" bash -c "
            export DJANGO_SETTINGS_MODULE=armguard.settings.production
            [[ -f '$ENV_FILE' ]] && set -a && source <(grep -v '^\s*#' '$ENV_FILE' | grep -E '^\s*\w+=') && set +a || true
            cd '$PROJECT_DIR'
            '$VENV_PYTHON' manage.py migrate --run-syncdb 2>&1
        " || echo "MIGRATE_FAILED")
        if echo "$migrate_out" | grep -q "MIGRATE_FAILED"; then
            warn "Django migrate failed — check .env credentials and PostgreSQL connection."
        else
            ok "Django migrations applied."
        fi
    else
        warn "Python venv not found at $VENV_PYTHON — skipping migration check."
        warn "Run manually after deploy: sudo -u $DEPLOY_USER $VENV_PYTHON $PROJECT_DIR/manage.py migrate"
    fi

    # ---------------------------------------------------------------------------
    step "6. Restart app service"
    # ---------------------------------------------------------------------------
    if systemctl list-units --full --all 2>/dev/null | grep -q "$SERVICE_NAME"; then
        systemctl start "$SERVICE_NAME" && ok "$SERVICE_NAME started." \
            || warn "Failed to start $SERVICE_NAME — start it manually."
        systemctl is-active --quiet "$SERVICE_NAME" \
            && ok "$SERVICE_NAME is running." \
            || warn "$SERVICE_NAME did not start — check: journalctl -u $SERVICE_NAME -n 50"
    else
        warn "$SERVICE_NAME not found — app is not deployed on this server yet."
        warn "Run deploy.sh first, then re-run this script with --restore-only."
    fi

    # ---------------------------------------------------------------------------
    echo
    echo -e "${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║              Recovery Complete                            ║${NC}"
    echo -e "${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo -e "  Backup source : $backup_dir"
    echo -e "  Target app    : $DEPLOY_DIR"
    echo -e "  Database      : $db_name (PostgreSQL)"
    echo
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo -e "  1. Review $ENV_FILE — update ALLOWED_HOSTS, SECRET_KEY, DB settings"
    echo -e "  2. Verify app: curl -sk https://localhost/ | head -5"
    echo -e "  3. Create superuser if needed:"
    echo -e "     sudo -u $DEPLOY_USER $VENV_PYTHON $PROJECT_DIR/manage.py createsuperuser"
    echo
}

# If --restore-only, run restore and exit (no SSH needed)
if [[ "$RESTORE_ONLY" == "true" ]]; then
    [[ -n "$CHOSEN_BACKUP" ]] || die "--restore-only requires --backup DIR"
    _do_restore "$CHOSEN_BACKUP"
    exit 0
fi

# ============================================================================
# TRANSFER MODE — runs on SOURCE server, SSHs to target
# ============================================================================
[[ $EUID -eq 0 ]] || die "Run as root: sudo $0"
command -v rsync &>/dev/null || die "'rsync' not found. Install: sudo apt install rsync"
command -v ssh   &>/dev/null || die "'ssh' not found."

# SSH options
SSH_OPTS="-p $SSH_PORT -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
[[ -n "$SSH_KEY" ]] && SSH_OPTS="$SSH_OPTS -i $SSH_KEY"
RSYNC_SSH="ssh $SSH_OPTS"

# ---------------------------------------------------------------------------
# Step 1: Pick a backup
# ---------------------------------------------------------------------------
step "Selecting backup"

if [[ -z "$CHOSEN_BACKUP" ]]; then
    declare -a BACKUP_DIRS BACKUP_LABELS

    _scan_dir() {
        local root="$1" prefix="$2"
        if [[ -d "$root" ]]; then
            while IFS= read -r dir; do
                local dump
                dump=$(find "$dir" -name "*.sql.gz" -o -name "*.sqlite3" 2>/dev/null | sort | tail -1 || true)
                [[ -z "$dump" ]] && continue
                local size
                size=$(du -sh "$dir" 2>/dev/null | awk '{print $1}' || echo "?")
                BACKUP_DIRS+=("$dir")
                BACKUP_LABELS+=("$prefix | $(basename "$dir") | $size")
            done < <(find "$root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -r)
        fi
    }

    _scan_dir "$BACKUP_ROOT"       "LOCAL   "
    if mountpoint -q /mnt/backup 2>/dev/null; then
        # Ensure armguard/ subdir is listable by non-root users
        chmod 755 "$EXTERNAL_BACKUP_DIR" 2>/dev/null || true
        _scan_dir "$EXTERNAL_BACKUP_DIR" "EXTERNAL"
    fi

    [[ ${#BACKUP_DIRS[@]} -gt 0 ]] || die "No backups found in $BACKUP_ROOT"

    echo -e "  ${BOLD}Available backups (newest first):${NC}"
    echo
    for i in "${!BACKUP_DIRS[@]}"; do
        printf "  [%2d] %s\n" "$((i+1))" "${BACKUP_LABELS[$i]}"
    done
    echo
    read -rp "  Select backup number: " _choice
    [[ "$_choice" =~ ^[0-9]+$ && "$_choice" -ge 1 && "$_choice" -le ${#BACKUP_DIRS[@]} ]] \
        || die "Invalid selection."
    CHOSEN_BACKUP="${BACKUP_DIRS[$(( _choice - 1 ))]}"
fi

log "Backup selected: $CHOSEN_BACKUP"
BACKUP_SIZE=$(du -sh "$CHOSEN_BACKUP" 2>/dev/null | awk '{print $1}' || echo "?")
log "Backup size    : $BACKUP_SIZE"

# Checksum on source before transfer
SHA_SRC=$(find "$CHOSEN_BACKUP" -name "*.sha256" 2>/dev/null | sort | tail -1 || true)
if [[ -n "$SHA_SRC" ]]; then
    log "Verifying source checksum …"
    (cd "$CHOSEN_BACKUP" && sha256sum -c "$(basename "$SHA_SRC")" --quiet 2>/dev/null) \
        && ok "Checksum OK." || warn "Source checksum MISMATCH — backup may be corrupted."
fi

# ---------------------------------------------------------------------------
# Step 2: Test SSH connectivity
# ---------------------------------------------------------------------------
step "Testing SSH connection to $TARGET"
# shellcheck disable=SC2086
ssh $SSH_OPTS "$TARGET" "echo OK" > /dev/null 2>&1 \
    || die "Cannot connect to $TARGET via SSH. Check credentials and --port/--key options."
ok "SSH connection OK."

# Get target hostname for display
TARGET_HOST=$(ssh $SSH_OPTS "$TARGET" "hostname" 2>/dev/null || echo "$TARGET")
log "Target hostname: $TARGET_HOST"

# ---------------------------------------------------------------------------
# Step 3: Transfer backup files
# ---------------------------------------------------------------------------
step "Transferring backup to $TARGET:$REMOTE_BACKUP_STAGING"

REMOTE_BACKUP_DIR="$REMOTE_BACKUP_STAGING/$(basename "$CHOSEN_BACKUP")"

# Create staging dir on target
# shellcheck disable=SC2086
ssh $SSH_OPTS "$TARGET" "sudo mkdir -p '$REMOTE_BACKUP_STAGING' && sudo chmod 755 '$REMOTE_BACKUP_STAGING'"

# Transfer the backup set
# shellcheck disable=SC2086
rsync -az --info=progress2 \
    -e "ssh $SSH_OPTS" \
    "$CHOSEN_BACKUP/" \
    "$TARGET:$REMOTE_BACKUP_DIR/" \
    || die "rsync transfer failed."
ok "Backup transferred → $TARGET:$REMOTE_BACKUP_DIR"

# Also transfer this script so target can run --restore-only
SCRIPT_PATH="$(realpath "$0")"
# shellcheck disable=SC2086
rsync -az -e "ssh $SSH_OPTS" "$SCRIPT_PATH" \
    "$TARGET:/tmp/transfer-to-server.sh" 2>/dev/null || true

if [[ "$TRANSFER_ONLY" == "true" ]]; then
    echo
    ok "Transfer complete (--transfer-only — no restore triggered)."
    echo
    echo -e "  To restore on the target server, run:"
    echo -e "  ${CYAN}ssh $TARGET${NC}"
    echo -e "  ${CYAN}sudo bash /tmp/transfer-to-server.sh --restore-only --backup $REMOTE_BACKUP_DIR${NC}"
    [[ "$SKIP_ENV"   == "true" ]] && echo -e "  ${CYAN}  (add --skip-env if .env is already configured)${NC}"
    [[ "$SKIP_MEDIA" == "true" ]] && echo -e "  ${CYAN}  (add --skip-media to skip media files)${NC}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 4: Run restore on target via SSH
# ---------------------------------------------------------------------------
step "Running restore on $TARGET"

RESTORE_CMD="sudo bash /tmp/transfer-to-server.sh --restore-only --backup '$REMOTE_BACKUP_DIR'"
[[ "$SKIP_ENV"   == "true" ]] && RESTORE_CMD="$RESTORE_CMD --skip-env"
[[ "$SKIP_MEDIA" == "true" ]] && RESTORE_CMD="$RESTORE_CMD --skip-media"

echo -e "  ${YELLOW}Command:${NC} $RESTORE_CMD"
echo

# shellcheck disable=SC2086
ssh $SSH_OPTS -t "$TARGET" "$RESTORE_CMD"

echo
ok "Recovery on $TARGET ($TARGET_HOST) complete."
echo
echo -e "  Verify the app is running:"
echo -e "  ${CYAN}ssh $TARGET 'sudo systemctl status armguard-gunicorn'${NC}"
echo -e "  ${CYAN}ssh $TARGET 'curl -sk https://localhost/ | head -5'${NC}"
echo
