#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Backup Retrieval Script
# =============================================================================
# Loads a backup into a temporary PostgreSQL database for safe read-only
# inspection WITHOUT touching the live 'armguard' database.
#
# Usage:
#   sudo bash scripts/retrieve-backup.sh
#   sudo bash scripts/retrieve-backup.sh --backup /var/backups/armguard/20260504_072232
#   sudo bash scripts/retrieve-backup.sh --query "SELECT * FROM personnel_personnel LIMIT 10"
#   sudo bash scripts/retrieve-backup.sh --export /tmp/export.csv --query "SELECT ..."
#
# What it does:
#   1. Lists available backup sets and lets you pick one
#   2. Creates a temporary database 'armguard_retrieve_<timestamp>'
#   3. Loads the backup into it
#   4. Opens psql (interactive) or runs your --query and exits
#   5. Drops the temporary database on exit
#
# The live 'armguard' database is never touched.
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKUP_ROOT="/var/backups/armguard"
EXTERNAL_BACKUP_DIR="/mnt/backup/armguard"
ENV_FILE="/var/www/ARMGUARD_RDS_V1/.env"
TEMP_DB="armguard_retrieve_$(date +%Y%m%d_%H%M%S)"
CHOSEN_BACKUP=""
QUERY=""
EXPORT_FILE=""

# ---------------------------------------------------------------------------
# Colours / logging
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[RETRIEVE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}    $*"; }
err()  { echo -e "${RED}[ERROR]${NC}   $*" >&2; }
ok()   { echo -e "${GREEN}[OK]${NC}     $*"; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup)  CHOSEN_BACKUP="$2"; shift 2 ;;
        --query)   QUERY="$2";         shift 2 ;;
        --export)  EXPORT_FILE="$2";   shift 2 ;;
        --help|-h)
            echo "Usage: sudo $0 [options]"
            echo "  --backup DIR     Path to a specific backup directory (skip menu)"
            echo "  --query  SQL     Run this SQL and exit instead of opening psql"
            echo "  --export FILE    Write --query output to FILE as CSV"
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root: sudo $0"
command -v psql     &>/dev/null || die "'psql' not found. Install: sudo apt install postgresql-client"
command -v gunzip   &>/dev/null || die "'gunzip' not found. Install: sudo apt install gzip"

# Load DB credentials from .env
DB_NAME="armguard"
DB_USER="armguard"
DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_PASS=""

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    source <(grep -v '^\s*#' "$ENV_FILE" | grep -E '^\s*\w+=') 2>/dev/null || true
    set +a
    DB_NAME="${DB_NAME:-armguard}"
    DB_USER="${DB_USER:-${DEPLOY_USER:-armguard}}"
    DB_HOST="${DB_HOST:-127.0.0.1}"
    DB_PORT="${DB_PORT:-5432}"
    DB_PASS="${DB_PASSWORD:-}"
fi

export PGPASSWORD="$DB_PASS"

# ---------------------------------------------------------------------------
# Helper: run psql as postgres superuser (for CREATE/DROP DATABASE)
# ---------------------------------------------------------------------------
pg_admin() { sudo -u postgres psql "$@"; }

# ---------------------------------------------------------------------------
# Helper: run psql against the temp DB as the armguard user
# ---------------------------------------------------------------------------
pg_temp() { PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TEMP_DB" "$@"; }

# ---------------------------------------------------------------------------
# Cleanup: always drop the temp DB on exit
# ---------------------------------------------------------------------------
_cleanup() {
    echo
    log "Cleaning up — dropping temporary database '$TEMP_DB' …"
    pg_admin -c "DROP DATABASE IF EXISTS $TEMP_DB;" 2>/dev/null && \
        ok "Temporary database dropped." || \
        warn "Could not drop '$TEMP_DB' — drop it manually: sudo -u postgres psql -c \"DROP DATABASE $TEMP_DB;\""
    unset PGPASSWORD
}
trap _cleanup EXIT

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      ArmGuard RDS V1 — Backup Retrieval                   ║${NC}"
echo -e "${BOLD}║      Live database is NOT affected                        ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
echo

# ---------------------------------------------------------------------------
# Step 1: Pick a backup
# ---------------------------------------------------------------------------
if [[ -z "$CHOSEN_BACKUP" ]]; then
    # Collect all backup sets from local + external (if mounted)
    declare -a BACKUP_DIRS BACKUP_LABELS

    _scan_dir() {
        local root="$1" label_prefix="$2"
        if [[ -d "$root" ]]; then
            while IFS= read -r dir; do
                local ts
                ts=$(basename "$dir")
                local dump
                dump=$(find "$dir" -name "*.sql.gz" -o -name "*.sqlite3" 2>/dev/null | sort | tail -1)
                [[ -z "$dump" ]] && continue
                local size
                size=$(du -sh "$dump" 2>/dev/null | awk '{print $1}' || echo "?")
                BACKUP_DIRS+=("$dir")
                BACKUP_LABELS+=("$label_prefix | $ts | $(basename "$dump") | $size")
            done < <(find "$root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -r)
        fi
    }

    _scan_dir "$BACKUP_ROOT"          "LOCAL   "
    mountpoint -q /mnt/backup 2>/dev/null && _scan_dir "$EXTERNAL_BACKUP_DIR" "EXTERNAL"

    if [[ ${#BACKUP_DIRS[@]} -eq 0 ]]; then
        die "No backups found in $BACKUP_ROOT or $EXTERNAL_BACKUP_DIR"
    fi

    echo -e "  ${BOLD}Available backups (newest first):${NC}"
    echo
    for i in "${!BACKUP_DIRS[@]}"; do
        printf "  [%2d] %s\n" "$((i+1))" "${BACKUP_LABELS[$i]}"
    done
    echo
    read -rp "  Select backup number: " choice

    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 || "$choice" -gt ${#BACKUP_DIRS[@]} ]]; then
        die "Invalid selection."
    fi

    CHOSEN_BACKUP="${BACKUP_DIRS[$((choice-1))]}"
fi

log "Selected backup: $CHOSEN_BACKUP"

# Locate the dump file
DUMP_FILE=$(find "$CHOSEN_BACKUP" -name "*.sql.gz" 2>/dev/null | sort | tail -1)
SQLITE_FILE=$(find "$CHOSEN_BACKUP" -name "*.sqlite3" 2>/dev/null | sort | tail -1)

if [[ -n "$DUMP_FILE" ]]; then
    log "Dump file  : $DUMP_FILE"
    BACKUP_TYPE="postgres"
elif [[ -n "$SQLITE_FILE" ]]; then
    log "SQLite file: $SQLITE_FILE"
    BACKUP_TYPE="sqlite"
else
    die "No .sql.gz or .sqlite3 dump found in $CHOSEN_BACKUP"
fi

# Verify SHA-256 if sidecar exists
SHA_FILE=$(find "$CHOSEN_BACKUP" -name "*.sha256" 2>/dev/null | sort | tail -1)
if [[ -n "$SHA_FILE" ]]; then
    log "Verifying checksum …"
    if (cd "$CHOSEN_BACKUP" && sha256sum -c "$(basename "$SHA_FILE")" --quiet 2>/dev/null); then
        ok "Checksum OK."
    else
        warn "Checksum MISMATCH — backup file may be corrupted. Proceeding anyway."
    fi
else
    warn "No .sha256 sidecar found — skipping integrity check."
fi

# ---------------------------------------------------------------------------
# Step 2: Create temporary database
# ---------------------------------------------------------------------------
log "Creating temporary database '$TEMP_DB' …"
pg_admin -c "CREATE DATABASE $TEMP_DB OWNER $DB_USER;" 2>/dev/null \
    || die "Failed to create temporary database. Is PostgreSQL running?"
ok "Temporary database created: $TEMP_DB"

# ---------------------------------------------------------------------------
# Step 3: Load the backup
# ---------------------------------------------------------------------------
log "Loading backup into '$TEMP_DB' …"

if [[ "$BACKUP_TYPE" == "postgres" ]]; then
    gunzip -c "$DUMP_FILE" | sudo -u postgres psql "$TEMP_DB" > /dev/null 2>&1 \
        && ok "Backup loaded successfully." \
        || warn "Load completed with warnings (may be harmless role/extension notices)."
else
    # SQLite: nothing to load into Postgres — offer direct sqlite3 inspection instead
    warn "This is a SQLite backup — it cannot be loaded into PostgreSQL."
    warn "To inspect it directly:"
    warn "  sqlite3 $SQLITE_FILE"
    warn "  .tables"
    warn "  SELECT * FROM personnel_personnel LIMIT 10;"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 4: Query or open interactive psql
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}  Temporary DB:${NC} $TEMP_DB"
echo -e "${BOLD}  Live DB:${NC}      $DB_NAME (UNTOUCHED)"
echo

if [[ -n "$QUERY" ]]; then
    log "Running query …"
    echo

    if [[ -n "$EXPORT_FILE" ]]; then
        PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TEMP_DB" \
            -c "\COPY ($QUERY) TO '$EXPORT_FILE' WITH CSV HEADER" \
            && ok "Results exported to: $EXPORT_FILE" \
            || die "Query failed."
    else
        pg_temp -c "$QUERY" || die "Query failed."
    fi
else
    # Interactive mode
    echo -e "  ${YELLOW}You are now connected to the BACKUP copy — the live database is safe.${NC}"
    echo -e "  ${YELLOW}Type \\q to exit. The temporary database will be auto-dropped on exit.${NC}"
    echo
    echo -e "  ${BOLD}Quick reference:${NC}"
    echo -e "  \\dt                                       — list all tables"
    echo -e "  SELECT * FROM personnel_personnel LIMIT 10;"
    echo -e "  SELECT item_id, model, serial_number, item_status FROM inventory_pistol;"
    echo -e "  SELECT item_id, model, serial_number, item_status FROM inventory_rifle;"
    echo -e "  SELECT * FROM transactions_transactionlogs WHERE log_status = 'Open';"
    echo -e "  SELECT * FROM users_auditlog ORDER BY timestamp DESC LIMIT 20;"
    echo
    pg_temp || true
fi

# Cleanup runs automatically via EXIT trap
