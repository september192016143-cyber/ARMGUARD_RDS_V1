#!/usr/bin/env bash
# =============================================================================
# ARMGUARD RDS V1 — Server Update Script
# =============================================================================
# Usage:
#   sudo ./update-server.sh [OPTIONS]
#
# Options:
#   --skip-migrate      Skip running database migrations
#   --skip-static       Skip collectstatic
#   --no-restart        Do not restart Gunicorn after update
#   --branch BRANCH     Git branch to pull (default: main)
#   --help              Show this help message
#
# What this script does:
#   1. Pulls latest code from git
#   2. Updates pip dependencies
#   3. Runs database migrations
#   4. Collects static files
#   5. Gracefully reloads Gunicorn (zero-downtime)
#   6. Verifies the service is healthy
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Constants (edit to match your deployment)
# ---------------------------------------------------------------------------
DEPLOY_USER="armguard"
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
PROJECT_DIR="$DEPLOY_DIR/project"
VENV_DIR="$DEPLOY_DIR/venv"
ENV_FILE="$DEPLOY_DIR/.env"
SERVICE_NAME="armguard-gunicorn"
LOG_DIR="/var/log/armguard"
BRANCH="main"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${BOLD}>>> $*${NC}"; }
die()     { error "$*"; exit 1; }

on_error() {
    error "Update failed at line $1. The service was NOT restarted."
    info "Check logs: journalctl -u $SERVICE_NAME -n 50"
    exit 1
}
trap 'on_error $LINENO' ERR

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SKIP_MIGRATE=false
SKIP_STATIC=false
NO_RESTART=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-migrate) SKIP_MIGRATE=true; shift ;;
        --skip-static)  SKIP_STATIC=true; shift ;;
        --no-restart)   NO_RESTART=true; shift ;;
        --branch)       BRANCH="$2"; shift 2 ;;
        --help|-h)
            grep '^#' "$0" | grep -E '^\# ' | sed 's/^# //'
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root: sudo $0"
[[ -d "$PROJECT_DIR" ]] || die "Project directory not found: $PROJECT_DIR"
[[ -f "$VENV_DIR/bin/python" ]] || die "Virtual environment not found: $VENV_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         ARMGUARD RDS V1 — Server Update                  ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
info "Timestamp : $TIMESTAMP"
info "Branch    : $BRANCH"

# ---------------------------------------------------------------------------
# 1. Pre-update backup
# ---------------------------------------------------------------------------
step "1/6 Pre-update database backup"

BACKUP_DIR="$DEPLOY_DIR/backups"
mkdir -p "$BACKUP_DIR"

if [[ -f "$PROJECT_DIR/db.sqlite3" ]]; then
    BACKUP_FILE="$BACKUP_DIR/pre-update-$TIMESTAMP.sqlite3"
    sudo -u "$DEPLOY_USER" "$VENV_PYTHON" - <<PYEOF
import sqlite3, shutil
src = "$PROJECT_DIR/db.sqlite3"
dst = "$BACKUP_FILE"
src_conn = sqlite3.connect(src)
dst_conn = sqlite3.connect(dst)
src_conn.backup(dst_conn)
src_conn.close()
dst_conn.close()
print(f"  Backup saved: $BACKUP_FILE")
PYEOF
    success "Pre-update backup created."
else
    warn "db.sqlite3 not found; skipping pre-update backup."
fi

# ---------------------------------------------------------------------------
# 2. Git pull
# ---------------------------------------------------------------------------
step "2/6 Pulling latest code (branch: $BRANCH)"

if [[ -d "$PROJECT_DIR/.git" ]]; then
    sudo -u "$DEPLOY_USER" git -C "$PROJECT_DIR" fetch --all
    sudo -u "$DEPLOY_USER" git -C "$PROJECT_DIR" checkout "$BRANCH"
    sudo -u "$DEPLOY_USER" git -C "$PROJECT_DIR" pull origin "$BRANCH"
    COMMIT=$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    success "Code updated to commit: $COMMIT"
elif [[ -d "$DEPLOY_DIR/.git" ]]; then
    sudo -u "$DEPLOY_USER" git -C "$DEPLOY_DIR" fetch --all
    sudo -u "$DEPLOY_USER" git -C "$DEPLOY_DIR" checkout "$BRANCH"
    sudo -u "$DEPLOY_USER" git -C "$DEPLOY_DIR" pull origin "$BRANCH"
    COMMIT=$(git -C "$DEPLOY_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    success "Code updated to commit: $COMMIT"
else
    warn "No git repository found. Skipping git pull."
    warn "Copy updated files to $PROJECT_DIR manually."
fi

# ---------------------------------------------------------------------------
# 3. Update Python dependencies
# ---------------------------------------------------------------------------
step "3/6 Updating Python dependencies"

REQUIREMENTS="$DEPLOY_DIR/requirements.txt"
[[ -f "$REQUIREMENTS" ]] || REQUIREMENTS="$PROJECT_DIR/requirements.txt"
[[ -f "$REQUIREMENTS" ]] || die "requirements.txt not found"

sudo -u "$DEPLOY_USER" "$VENV_PIP" install --upgrade pip --quiet
sudo -u "$DEPLOY_USER" "$VENV_PIP" install -r "$REQUIREMENTS" --quiet
sudo -u "$DEPLOY_USER" "$VENV_PIP" install gunicorn --quiet  # ensure gunicorn present

success "Dependencies updated."

# ---------------------------------------------------------------------------
# 4. Database migrations
# ---------------------------------------------------------------------------
if [[ "$SKIP_MIGRATE" == "false" ]]; then
    step "4/6 Running database migrations"
    sudo -u "$DEPLOY_USER" bash -c "
        export DJANGO_SETTINGS_MODULE=armguard.settings.production
        [[ -f '$ENV_FILE' ]] && set -a && source <(grep -v '^\s*#' '$ENV_FILE' | grep '=') && set +a
        cd '$PROJECT_DIR'
        '$VENV_PYTHON' manage.py migrate --noinput
    "
    success "Migrations complete."
else
    info "Skipping migrations (--skip-migrate)."
fi

# ---------------------------------------------------------------------------
# 5. Collect static files
# ---------------------------------------------------------------------------
if [[ "$SKIP_STATIC" == "false" ]]; then
    step "5/6 Collecting static files"
    sudo -u "$DEPLOY_USER" bash -c "
        export DJANGO_SETTINGS_MODULE=armguard.settings.production
        [[ -f '$ENV_FILE' ]] && set -a && source <(grep -v '^\s*#' '$ENV_FILE' | grep '=') && set +a
        cd '$PROJECT_DIR'
        '$VENV_PYTHON' manage.py collectstatic --noinput --clear
    "
    success "Static files collected."
else
    info "Skipping collectstatic (--skip-static)."
fi

# ---------------------------------------------------------------------------
# 6. Reload Gunicorn (graceful — zero downtime)
# ---------------------------------------------------------------------------
if [[ "$NO_RESTART" == "false" ]]; then
    step "6/6 Reloading Gunicorn service"
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        # HUP = graceful reload; workers finish current requests before cycling
        systemctl reload "$SERVICE_NAME" 2>/dev/null || systemctl restart "$SERVICE_NAME"
        sleep 2
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            success "Gunicorn reloaded successfully."
        else
            error "Gunicorn failed to restart!"
            journalctl -u "$SERVICE_NAME" -n 20 --no-pager
            exit 1
        fi
    else
        warn "Service '$SERVICE_NAME' was not running. Starting it..."
        systemctl start "$SERVICE_NAME"
        success "Gunicorn started."
    fi
else
    info "Skipping service restart (--no-restart)."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo -e "${GREEN}${BOLD}Update complete.${NC}"
info "Timestamp : $TIMESTAMP"
[[ -n "${COMMIT:-}" ]] && info "Git commit : $COMMIT"
info "Service   : $(systemctl is-active $SERVICE_NAME)"
info "Logs      : journalctl -u $SERVICE_NAME -f"
