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
#   4. Runs database migrations and setup_groups
#   5. Downloads Font Awesome 6.5.0 locally (no CDN tracking warnings)
#   6. Collects static files
#   7. Cleans up test QR code files (P-TEST-*.png) to prevent git conflicts
#   8. Gracefully reloads Gunicorn (zero-downtime)
#   9. Verifies the service is healthy
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

# ---------------------------------------------------------------------------
# Helper: delete all test-generated QR code PNG files.
# Must be called BEFORE git stash so these files are never stashed and
# re-applied on stash pop (which would recreate the modify/delete conflict).
# Also called as step 5b after deployment as a second safety pass.
# ---------------------------------------------------------------------------
_clean_test_media_files() {
    local media_dir="$1/media"
    [[ -d "$media_dir" ]] || return 0

    # All file-name patterns produced when Django tests create Personnel/Pistol/Rifle
    # records.  Extend this list if new test IDs are added to the test suite.
    local count
    count=$(find "$media_dir" \( \
        -name "P-TEST-*.png"   -o -name "P-MAG-*.png"  \
        -o -name "P-INT-*.png"  -o -name "P-ATOM-*.png" \
        -o -name "P-SVC-*.png"  -o -name "P-PERS-*.png" \
        -o -name "P-AUDIT-*.png" \
        -o -name "IP-*-TEST-*.png"  -o -name "IP-*-AUDIT-*.png" \
        -o -name "IP-*-INT-*.png"   -o -name "IP-*-ATOM-*.png"  \
        -o -name "IP-*-SVC-*.png"   -o -name "IP-*-MAG-*.png"   \
        -o -name "IP-*-AVAIL-*.png" \
        -o -name "IR-*-TEST-*.png"  -o -name "IR-*-AUDIT-*.png" \
    \) -type f 2>/dev/null | wc -l)

    if [[ "$count" -gt 0 ]]; then
        find "$media_dir" \( \
            -name "P-TEST-*.png"   -o -name "P-MAG-*.png"  \
            -o -name "P-INT-*.png"  -o -name "P-ATOM-*.png" \
            -o -name "P-SVC-*.png"  -o -name "P-PERS-*.png" \
            -o -name "P-AUDIT-*.png" \
            -o -name "IP-*-TEST-*.png"  -o -name "IP-*-AUDIT-*.png" \
            -o -name "IP-*-INT-*.png"   -o -name "IP-*-ATOM-*.png"  \
            -o -name "IP-*-SVC-*.png"   -o -name "IP-*-MAG-*.png"   \
            -o -name "IP-*-AVAIL-*.png" \
            -o -name "IR-*-TEST-*.png"  -o -name "IR-*-AUDIT-*.png" \
        \) -type f -delete 2>/dev/null
        info "  Removed $count test QR code file(s) from media/"
    fi
}

# Fix ownership so the armguard user can write to .git/objects
# (Happens when root previously cloned the repo or ran git operations)
_git_pull_repo() {
    local repo_dir="$1"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$repo_dir/.git"

    # ── KEY FIX: remove test-generated QR files BEFORE stash ─────────────────
    # If Django tests ran on this server, they created P-TEST-*.png, P-MAG-*.png,
    # etc. in media/. Git sees these as untracked/modified and stashes them.
    # When stash pop runs after the pull, the files come back — recreating the
    # exact modify/delete conflict we're trying to prevent. Deleting them here
    # means the stash never captures them.
    _clean_test_media_files "$repo_dir"

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

    # Remove any untracked files whose paths are being introduced by the incoming
    # commits (git refuses to pull if it would overwrite them).
    local incoming_files
    incoming_files=$(sudo -u "$DEPLOY_USER" git -C "$repo_dir" \
        diff --name-only HEAD "origin/$BRANCH" 2>/dev/null || true)
    if [[ -n "$incoming_files" ]]; then
        while IFS= read -r f; do
            local full_path="$repo_dir/$f"
            # Only remove if untracked (not already in the index)
            if [[ -f "$full_path" ]] && \
               ! sudo -u "$DEPLOY_USER" git -C "$repo_dir" \
                   ls-files --error-unmatch "$f" &>/dev/null 2>&1; then
                rm -f "$full_path"
                warn "Removed untracked file that would block pull: $f"
            fi
        done <<< "$incoming_files"
    fi

    # Retry git pull up to 3 times with backoff (guards against transient
    # GitHub HTTP 500 / connection errors that abort the script under pipefail).
    local _pull_ok=false
    for _attempt in 1 2 3; do
        if sudo -u "$DEPLOY_USER" git -C "$repo_dir" pull origin "$BRANCH"; then
            _pull_ok=true
            break
        fi
        warn "git pull attempt $_attempt failed. Retrying in $(( _attempt * 5 ))s..."
        sleep $(( _attempt * 5 ))
    done
    if [[ "$_pull_ok" == "false" ]]; then
        # All retries failed — fall back to hard reset to origin so the script
        # can continue with whatever fetch already downloaded.
        warn "git pull failed after 3 attempts. Resetting to origin/$BRANCH (fetched objects are local)."
        sudo -u "$DEPLOY_USER" git -C "$repo_dir" reset --hard "origin/$BRANCH"
    fi

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
# 2b. Deploy Nginx config (copy from repo to sites-available and reload)
# ---------------------------------------------------------------------------
step "2b/8 Deploying Nginx config"

NGINX_SRC="$DEPLOY_DIR/scripts/nginx-armguard-ssl-lan.conf"
NGINX_DEST="/etc/nginx/sites-available/armguard-ssl-lan"
NGINX_DEST_ALT="/etc/nginx/sites-available/armguard"

# Determine which destination file is currently symlinked/active
if [[ -f "$NGINX_DEST_ALT" ]] && [[ ! -f "$NGINX_DEST" ]]; then
    NGINX_DEST="$NGINX_DEST_ALT"
fi

if [[ -f "$NGINX_SRC" ]]; then
    cp "$NGINX_SRC" "$NGINX_DEST"
    # Ensure .mjs → JavaScript MIME type is registered in the system mime.types.
    # Nginx 1.24 on Ubuntu 24.04 does not ship .mjs in its mime.types.
    # Ubuntu 24.04 Nginx uses 'application/javascript' (not 'text/javascript');
    # we handle both. A new standalone line is added as final fallback.
    if ! grep -qE '\bmjs\b' /etc/nginx/mime.types 2>/dev/null; then
        if grep -q 'application/javascript' /etc/nginx/mime.types; then
            sed -i 's/\(application\/javascript[^;]*\);/\1 mjs;/' /etc/nginx/mime.types
        elif grep -q 'text/javascript' /etc/nginx/mime.types; then
            sed -i 's/\(text\/javascript[^;]*\);/\1 mjs;/' /etc/nginx/mime.types
        else
            # Neither entry found — insert a standalone line before closing }
            sed -i '/^}/i\    text/javascript                       mjs;' /etc/nginx/mime.types
        fi
        if grep -qE '\bmjs\b' /etc/nginx/mime.types; then
            info ".mjs MIME type added to /etc/nginx/mime.types"
        else
            warn "Could not patch /etc/nginx/mime.types for .mjs — check manually"
        fi
    fi
    if nginx -t 2>/dev/null; then
        systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null || true
        success "Nginx config deployed and reloaded."
    else
        warn "Nginx config test failed — reverting."
        nginx -t
    fi
else
    warn "Nginx config not found at $NGINX_SRC — skipping."
fi

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
        '$VENV_PYTHON' manage.py makemigrations --noinput
        '$VENV_PYTHON' manage.py migrate --noinput
        '$VENV_PYTHON' manage.py setup_groups
        '$VENV_PYTHON' manage.py backfill_user_groups
    "
    success "Migrations, group setup, and user backfill complete."
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
# 5b. Clean up test QR code files (prevent git conflicts)
# ---------------------------------------------------------------------------
step "5b/8 Cleaning up test QR code files"

# Second pass using the same comprehensive function used before git pull.
# Catches any files created by tests between deployments that may have slipped
# through (e.g. tests run as root after the pre-pull cleanup).
_clean_test_media_files "$PROJECT_DIR"
success "Test QR code cleanup complete."

# ---------------------------------------------------------------------------
# 6. Re-run Gunicorn auto-tuner (recomputes workers/threads after any change)
# ---------------------------------------------------------------------------
if [[ -f "/usr/local/bin/gunicorn-autoconf.sh" ]]; then
    step "6/8 Re-running Gunicorn auto-tuner"
    bash /usr/local/bin/gunicorn-autoconf.sh
    success "Worker count recomputed."
elif [[ -f "$DEPLOY_DIR/scripts/gunicorn-autoconf.sh" ]]; then
    step "6/8 Re-running Gunicorn auto-tuner (from scripts/)"
    bash "$DEPLOY_DIR/scripts/gunicorn-autoconf.sh"
    success "Worker count recomputed."
fi

# ---------------------------------------------------------------------------
# 7. Reload Gunicorn (graceful — zero downtime)
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

# HTTP endpoint check — verifies the app actually responds (not just systemd state).
HEALTH_URL="http://127.0.0.1:8000/health/"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "000")
if [[ "$HTTP_STATUS" =~ ^2 ]]; then
    success "Health endpoint $HEALTH_URL returned HTTP $HTTP_STATUS."
elif [[ "$HTTP_STATUS" =~ ^3 ]]; then
    # 3xx redirect (e.g. SECURE_SSL_REDIRECT=True) still means the app is alive.
    success "Health endpoint $HEALTH_URL returned HTTP $HTTP_STATUS (redirect — service alive)."
elif [[ "$HTTP_STATUS" == "000" ]]; then
    warn "Could not reach $HEALTH_URL (curl failed). Check if /health/ URL is configured."
else
    warn "Health endpoint returned HTTP $HTTP_STATUS (expected 2xx/3xx)."
    HEALTH_OK=false
fi

# ---------------------------------------------------------------------------
# Ensure consolidated backup cron is installed / up-to-date
# ---------------------------------------------------------------------------
BACKUP_SH_PATH="$DEPLOY_DIR/scripts/backup.sh"
if [[ -f "$BACKUP_SH_PATH" ]]; then
    # Use a temp file instead of a pipe so crontab -l's non-zero exit code
    # (no existing crontab) cannot propagate through set -Eo pipefail and
    # fire on_error via the inherited ERR trap inside the subshell.
    _CRON_TMP=$(mktemp)
    crontab -l 2>/dev/null | grep -v 'backup.sh' > "$_CRON_TMP" || true
    printf '0 */3 * * * nice -n 19 ionice -c 3 %s >> %s/backup.log 2>&1\n' \
        "$BACKUP_SH_PATH" "$LOG_DIR" >> "$_CRON_TMP"
    crontab "$_CRON_TMP"
    rm -f "$_CRON_TMP"
    success "Backup cron verified: every 3 hours (nice -n 19 ionice -c 3)."
fi

# ---------------------------------------------------------------------------
# Post-update storage summary
# ---------------------------------------------------------------------------
echo
step "Storage Summary"

# Disk usage on the deployment partition
df -h "$DEPLOY_DIR" | awk 'NR==1{next} {printf "  Disk : %s used of %s  (%s free,  %s used)\n",$3,$2,$4,$5}'

# Media folder sizes (sorted by size)
MEDIA_DIR="$PROJECT_DIR/media"
if [[ -d "$MEDIA_DIR" ]]; then
    echo "  Media breakdown:"
    du -sh "$MEDIA_DIR"/*/  2>/dev/null | sort -rh | awk '{printf "    %-35s %s\n",$2,$1}'
    echo "  Media total: $(du -sh "$MEDIA_DIR" 2>/dev/null | cut -f1)"
fi

# SQLite database size
DB_FILE="$PROJECT_DIR/db.sqlite3"
if [[ -f "$DB_FILE" ]]; then
    DB_SIZE=$(du -sh "$DB_FILE" 2>/dev/null | cut -f1)
    echo "  Database (sqlite3): $DB_SIZE"
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
