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
#   1. Creates a pre-update database backup
#   2. Pulls latest code from git
#   3. Updates pip dependencies
#   4. Runs database migrations
#   5. Downloads Font Awesome 6.5.0 locally (no CDN tracking warnings)
#   6. Collects static files
#   7. Gracefully reloads Gunicorn (zero-downtime)
#   8. Verifies the service is healthy
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
step "1/8 Pre-update database backup"

BACKUP_DIR="$DEPLOY_DIR/backups"
mkdir -p "$BACKUP_DIR"

if [[ -f "$PROJECT_DIR/db.sqlite3" ]]; then
    BACKUP_FILE="$BACKUP_DIR/pre-update-$TIMESTAMP.sqlite3"
    # Use cp for the backup — avoids the sqlite3 Python heredoc variable expansion
    # issue when running as a different user via sudo -u.
    cp "$PROJECT_DIR/db.sqlite3" "$BACKUP_FILE"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$BACKUP_FILE"
    info "  Backup saved: $BACKUP_FILE"
    success "Pre-update backup created."
else
    warn "db.sqlite3 not found; skipping pre-update backup."
fi

# ---------------------------------------------------------------------------
# 2. Git pull
# ---------------------------------------------------------------------------
step "2/8 Pulling latest code (branch: $BRANCH)"

# Pre-emptively remove generated/downloaded files that are never meant to be
# tracked by git. If a previous update failed mid-way, these can end up as
# unmerged (conflicted) index entries that block both 'git stash' and 'git pull'.
_REPO_DIR="$DEPLOY_DIR"
[[ -d "$PROJECT_DIR/.git" ]] && _REPO_DIR="$PROJECT_DIR"
rm -f "$_REPO_DIR/project/armguard/static/css/fontawesome/all.min.css"
sudo -u "$DEPLOY_USER" git -C "$_REPO_DIR" rm --cached -f \
    project/armguard/static/css/fontawesome/all.min.css 2>/dev/null || true
unset _REPO_DIR

# Fix ownership so the armguard user can write to .git/objects
# (Happens when root previously cloned the repo or ran git operations)
_git_pull_repo() {
    local repo_dir="$1"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$repo_dir/.git"

    # Clear any unmerged/conflicted index entries left by previous failed merges.
    # These block both 'git stash' and 'git pull'. Generated files (e.g. fontawesome
    # downloaded by this script) should never be tracked anyway.
    local unmerged
    unmerged=$(sudo -u "$DEPLOY_USER" git -C "$repo_dir" ls-files --unmerged 2>/dev/null \
               | awk '{print $4}' | sort -u)
    if [[ -n "$unmerged" ]]; then
        while IFS= read -r uf; do
            rm -f "$repo_dir/$uf"
            sudo -u "$DEPLOY_USER" git -C "$repo_dir" rm --cached -f "$uf" 2>/dev/null || true
            warn "Cleared conflicted index entry: $uf"
        done <<< "$unmerged"
    fi

    # Stash any local changes (e.g. production settings overrides) so pull never aborts
    local stashed=false
    local dirty
    dirty=$(sudo -u "$DEPLOY_USER" git -C "$repo_dir" status --porcelain 2>/dev/null || true)
    if [[ -n "$dirty" ]]; then
        sudo -u "$DEPLOY_USER" git -C "$repo_dir" \
            -c user.email="armguard@localhost" -c user.name="armguard" \
            stash 2>&1 && stashed=true || true
    fi

    sudo -u "$DEPLOY_USER" git -C "$repo_dir" fetch --all
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" checkout "$BRANCH"
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" pull origin "$BRANCH"

    # Restore local changes (e.g. production settings overrides)
    if [[ "$stashed" == "true" ]]; then
        sudo -u "$DEPLOY_USER" git -C "$repo_dir" \
            -c user.email="armguard@localhost" -c user.name="armguard" \
            stash pop || \
            warn "Stash pop had conflicts — review manually: git -C $repo_dir stash show"
    fi

    # Eliminate CRLF line-ending noise: files committed from Windows show as
    # "modified" on Linux because of CR characters. Disable autocrlf and reset
    # all tracked files to the LF copies stored in the repo.
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" config core.autocrlf false
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" checkout -- . 2>/dev/null || true

    COMMIT=$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    success "Code updated to commit: $COMMIT"
}

if [[ -d "$PROJECT_DIR/.git" ]]; then
    _git_pull_repo "$PROJECT_DIR"
elif [[ -d "$DEPLOY_DIR/.git" ]]; then
    _git_pull_repo "$DEPLOY_DIR"
else
    warn "No git repository found. Skipping git pull."
    warn "Copy updated files to $PROJECT_DIR manually."
fi

# ---------------------------------------------------------------------------
# 3. Update Python dependencies
# ---------------------------------------------------------------------------
step "3/8 Updating Python dependencies"

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
    step "4/8 Running database migrations"
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
# 4b. Download Font Awesome locally (eliminates CDN tracking-prevention warning)
# ---------------------------------------------------------------------------
step "5/8 Downloading Font Awesome 6.5.0 to local static files"

FA_VERSION="6.5.0"
FA_BASE_URL="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/${FA_VERSION}"
FA_CSS_DIR="$PROJECT_DIR/armguard/static/css/fontawesome"
FA_WEBFONTS_DIR="$FA_CSS_DIR/webfonts"

FA_WEBFONTS=(
    "fa-brands-400.woff2"
    "fa-brands-400.ttf"
    "fa-regular-400.woff2"
    "fa-regular-400.ttf"
    "fa-solid-900.woff2"
    "fa-solid-900.ttf"
    "fa-v4compatibility.woff2"
    "fa-v4compatibility.ttf"
)

mkdir -p "$FA_CSS_DIR" "$FA_WEBFONTS_DIR"

if wget -q --timeout=30 -O "$FA_CSS_DIR/all.min.css" "${FA_BASE_URL}/css/all.min.css"; then
    sed -i 's|\.\./webfonts/|webfonts/|g' "$FA_CSS_DIR/all.min.css"
    success "Font Awesome CSS downloaded."
else
    warn "Failed to download Font Awesome CSS. Icons may fall back to CDN."
fi

FA_FONT_FAILURES=0
for font in "${FA_WEBFONTS[@]}"; do
    if ! wget -q --timeout=30 -O "$FA_WEBFONTS_DIR/$font" "${FA_BASE_URL}/webfonts/${font}"; then
        warn "Failed to download webfont: $font"
        FA_FONT_FAILURES=$((FA_FONT_FAILURES + 1))
    fi
done

sudo -u "$DEPLOY_USER" true 2>/dev/null && chown -R "$DEPLOY_USER:$DEPLOY_USER" "$FA_CSS_DIR" || true

if [[ "$FA_FONT_FAILURES" -eq 0 ]]; then
    success "All Font Awesome webfonts downloaded."
else
    warn "$FA_FONT_FAILURES webfont(s) failed to download."
fi

# ---------------------------------------------------------------------------
# 5. Collect static files
# ---------------------------------------------------------------------------
if [[ "$SKIP_STATIC" == "false" ]]; then
    step "6/8 Collecting static files"
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
    step "7/8 Reloading Gunicorn service"
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
# 8. Post-update health check
# ---------------------------------------------------------------------------
step "8/8 Post-update health check"

HEALTH_OK=true
if systemctl is-active --quiet "$SERVICE_NAME"; then
    success "Gunicorn ($SERVICE_NAME) is running."
else
    error "Gunicorn is NOT running!"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    HEALTH_OK=false
fi

if systemctl is-active --quiet nginx; then
    success "Nginx is running."
else
    warn "Nginx is not running. Check: journalctl -u nginx -n 20"
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
