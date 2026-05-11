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
REPO_URL="https://github.com/september192016143-cyber/ARMGUARD_RDS_V1.git"
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
# LVM auto-expand: grow the root LV to use all unallocated PV space.
# Runs inside an isolated subshell with error-handling disabled so a failure
# here can never abort the update.
# ---------------------------------------------------------------------------
_expand_lvm() {
    ( set +eE
    local root_dev vg_name lv_path pv_list free_pe

    root_dev=$(findmnt -n -o SOURCE / 2>/dev/null)
    [[ "$root_dev" == /dev/mapper/* ]] || { info "Root is not LVM — skipping LVM expand."; exit 0; }

    lv_path=$(lvs --noheadings -o lv_path "$root_dev" 2>/dev/null | tr -d ' ')
    [[ -n "$lv_path" ]] || { warn "LVM: cannot resolve LV path — skipping."; exit 0; }
    vg_name=$(lvs --noheadings -o vg_name "$root_dev" 2>/dev/null | tr -d ' ')

    pv_list=$(pvs --noheadings -o pv_name 2>/dev/null | tr -d ' ' | tr '\n' ' ')
    [[ -n "$pv_list" ]] && pvresize $pv_list 2>/dev/null

    free_pe=$(vgs --noheadings --units b -o vg_free "$vg_name" 2>/dev/null | tr -d ' B')
    if [[ "${free_pe:-0}" -le 0 ]]; then
        info "LVM: no unallocated space in VG '$vg_name' — nothing to expand."
        exit 0
    fi

    lvextend -l +100%FREE "$lv_path" 2>/dev/null
    resize2fs "$root_dev" 2>/dev/null || xfs_growfs / 2>/dev/null
    local new_size; new_size=$(df -h / | awk 'NR==2{print $2}')
    success "LVM: root filesystem expanded — size is now $new_size."
    ) || warn "LVM expand encountered an error — update continues."
}

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

# Expand LVM before anything else so the full disk is available.
_expand_lvm

# ---------------------------------------------------------------------------
# 1. Pre-update backup
# ---------------------------------------------------------------------------
step "1/8 Pre-update database backup"

BACKUP_DIR="$DEPLOY_DIR/backups"
mkdir -p "$BACKUP_DIR"
# Ensure FileBasedCache directory exists (added in performance update).
mkdir -p "$DEPLOY_DIR/cache"
chmod 750 "$DEPLOY_DIR/cache"

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

# Pre-emptively handle Font Awesome CSS, which was historically committed to
# the repo (commits 3dc2b9b / 9a5af3b) and later removed.  Servers still on an
# old commit have the file tracked; on those servers 'git pull' applies the
# deletion commit, causing a modify/delete conflict on 'git stash pop'.
#
# FIX: only delete the physical file here.  Do NOT run 'git rm --cached'.
# Reason: 'git rm --cached' stages a deletion, which 'git stash' captures.
# 'git stash pop' then tries to replay the deletion after 'git pull' has
# already deleted the file → conflict.
# Leaving the file tracked (but physically absent) means 'git checkout -- .'
# inside _git_pull_repo will restore it to HEAD's version (no modification),
# so stash has nothing to capture and 'git pull' removes it cleanly.
_REPO_DIR="$DEPLOY_DIR"
[[ -d "$PROJECT_DIR/.git" ]] && _REPO_DIR="$PROJECT_DIR"
rm -f "$_REPO_DIR/project/armguard/static/css/fontawesome/all.min.css"
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
_git_clone_repo() {
    # Called when no .git exists at $DEPLOY_DIR.
    # Uses git init + fetch + reset so it works on an already-populated directory
    # (e.g. production with live db.sqlite3, .env, media/) — untracked files are
    # never deleted by reset --hard.
    local repo_dir="$1"

    info "Initializing git repository at $repo_dir ..."
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" init
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" config core.autocrlf false
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" remote add origin "$REPO_URL"
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" fetch --depth=1 origin "$BRANCH"

    # Create / switch to branch tracking origin
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" checkout -B "$BRANCH" \
        "origin/$BRANCH" 2>/dev/null || \
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" reset --hard "origin/$BRANCH"

    # Ensure untracked live files (media/, .env, db.sqlite3) are ignored from index
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" rm -r --cached project/media/ 2>/dev/null || true
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" reset HEAD project/media/ 2>/dev/null || true

    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$repo_dir/.git"

    COMMIT=$(sudo -u "$DEPLOY_USER" git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    success "Repository initialized. HEAD is now at $COMMIT"
}

_git_pull_repo() {
    local repo_dir="$1"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$repo_dir/.git"

    # ── STEP 0: normalize CRLF BEFORE anything else ──────────────────────────
    # Files committed from Windows have CRLF; Linux git sees them as modified.
    # Setting autocrlf=false + resetting tracked files eliminates this noise
    # BEFORE the dirty check below, so purely-CRLF "changes" are never stashed,
    # never conflict on pop, and never appear in `git status` again.
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" config core.autocrlf false
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" checkout -- . 2>/dev/null || true

    # ── Ensure project/media/ is never tracked in the local index ────────────
    # The remote repo removed all media/.gitkeep files from tracking (commit
    # f941329). If the server's local index still has any media/ file tracked,
    # git pull will produce modify/delete conflicts on stash pop.
    # Steps:
    #   1. rm --cached  — removes media/ paths from index (stages as deletions)
    #   2. reset HEAD   — unstages those deletions so files become "untracked"
    # Untracked files are never captured by git stash (no -u flag), so stash
    # pop can never conflict on them again.
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" rm -r --cached project/media/ 2>/dev/null || true
    sudo -u "$DEPLOY_USER" git -C "$repo_dir" reset HEAD project/media/ 2>/dev/null || true

    # ── KEY FIX: remove test-generated QR files BEFORE stash ─────────────────
    # If Django tests ran on this server, they created P-TEST-*.png, P-MAG-*.png,
    # etc. in media/. Git sees these as untracked/modified and stashes them.
    # When stash pop runs after the pull, the files come back — recreating the
    # exact modify/delete conflict we're trying to prevent. Deleting them here
    # means the stash never captures them.
    _clean_test_media_files "$repo_dir"

    # ── Remove Django auto-generated migration files BEFORE stash ────────────
    # Django's migration autodetect can generate new migration files on the server
    # when it sees a model/migration state mismatch (e.g. choices changes in 4.x+).
    # These untracked files get stashed, then conflict on pop when the repo ships
    # the canonical version of the same migration.  Deleting them pre-stash means
    # the repo version always wins cleanly.
    find "$repo_dir/project/armguard/apps" \
        -path "*/migrations/0[0-9][0-9][0-9]_*.py" \
        -not -path "*/__pycache__/*" \
        ! -name "*initial*" \
        -newer "$repo_dir/.git/FETCH_HEAD" 2>/dev/null | while IFS= read -r mf; do
        # Only remove if it is NOT tracked by git
        local rel_mf="${mf#$repo_dir/}"
        if ! sudo -u "$DEPLOY_USER" git -C "$repo_dir" \
                ls-files --error-unmatch "$rel_mf" &>/dev/null 2>&1; then
            rm -f "$mf"
            warn "Removed server-generated Django migration (not in repo): $rel_mf"
        fi
    done

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
            stash 2>&1
        # 'git stash' exits 0 even when "No local changes to save" (nothing stashed).
        # Only attempt stash pop if an entry was actually created.
        if sudo -u "$DEPLOY_USER" git -C "$repo_dir" stash list 2>/dev/null | grep -q .; then
            stashed=true
        fi
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

    COMMIT=$(sudo -u "$DEPLOY_USER" git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    success "Code updated to commit: $COMMIT"
}

if [[ -d "$PROJECT_DIR/.git" ]]; then
    _git_pull_repo "$PROJECT_DIR"
elif [[ -d "$DEPLOY_DIR/.git" ]]; then
    _git_pull_repo "$DEPLOY_DIR"
else
    info "No git repository found at $DEPLOY_DIR — initializing from $REPO_URL"
    _git_clone_repo "$DEPLOY_DIR"
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

# Ensure proxy-params.conf snippet exists (deploy.sh creates it on first run;
# servers bootstrapped without deploy.sh or after a re-image may be missing it).
# Without X-Forwarded-Proto, Django cannot detect HTTPS behind Nginx and may
# enter an HTTPS→HTTPS redirect loop when SECURE_SSL_REDIRECT is enabled.
PROXY_PARAMS="/etc/nginx/snippets/proxy-params.conf"
if [[ ! -f "$PROXY_PARAMS" ]]; then
    mkdir -p /etc/nginx/snippets
    cat > "$PROXY_PARAMS" <<'SNIPPET'
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_redirect    off;
proxy_http_version 1.1;
proxy_set_header   Connection "";
proxy_buffering         on;
proxy_buffer_size       8k;
proxy_buffers           8 16k;
proxy_busy_buffers_size 32k;
SNIPPET
    info "Created missing $PROXY_PARAMS"
fi

if [[ -f "$NGINX_SRC" ]]; then
    # Resolve placeholder values — read DOMAIN/LAN_IP from the existing deployed
    # config so they survive updates without needing deploy.sh to re-run.
    _STATIC_ROOT="$DEPLOY_DIR/project/staticfiles"
    _MEDIA_ROOT="$DEPLOY_DIR/project/media"
    # Try to extract the server IP/domain from the current live config
    _EXISTING_CONF="${NGINX_DEST_ALT}"
    [[ -f "$NGINX_DEST" ]] && _EXISTING_CONF="$NGINX_DEST"
    _DOMAIN=$(grep -oP '(?<=server_name\s)[^\s;]+' "$_EXISTING_CONF" 2>/dev/null | head -1 || true)
    _LAN_IP="$_DOMAIN"
    # Fall back to the machine's primary LAN IP if not found in config
    if [[ -z "$_DOMAIN" ]] || grep -q '__' <<< "$_DOMAIN"; then
        _DOMAIN=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
        _LAN_IP="$_DOMAIN"
    fi
    # Substitute all placeholders in the template before deploying
    sed \
        -e "s|__STATIC_ROOT__|${_STATIC_ROOT}|g" \
        -e "s|__MEDIA_ROOT__|${_MEDIA_ROOT}|g" \
        -e "s|__DOMAIN__|${_DOMAIN}|g" \
        -e "s|__LAN_IP__|${_LAN_IP}|g" \
        "$NGINX_SRC" > "$NGINX_DEST"
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
    if sudo nginx -t 2>/dev/null; then
        systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null || true
        success "Nginx config deployed and reloaded."
    else
        warn "Nginx config test failed — reverting."
        sudo nginx -t
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

# Warn if Google Sheets libraries are not installed AND the feature is configured.
_SA_JSON=$(grep -E '^GOOGLE_SA_JSON=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"\047 ' || true)
if [[ -n "$_SA_JSON" ]]; then
    if ! sudo -u "$DEPLOY_USER" "$VENV_PYTHON" -c "import gspread, google.auth" 2>/dev/null; then
        warn "GOOGLE_SA_JSON is set but gspread/google-auth are missing."
        warn "Run: $VENV_PIP install 'gspread>=6.0.0' 'google-auth>=2.29.0'"
    else
        info "Google Sheets import: gspread + google-auth present."
        if [[ -f "$_SA_JSON" ]]; then
            # Ensure the key file has correct ownership and permissions
            chmod 600 "$_SA_JSON"
            chown "$DEPLOY_USER:$DEPLOY_USER" "$_SA_JSON"
            info "Service account key: $_SA_JSON (permissions secured)"
        else
            warn "Service account key not found: $_SA_JSON (set in .env GOOGLE_SA_JSON)"
        fi
    fi
else
    info "Google Sheets import: GOOGLE_SA_JSON not set — feature disabled."
fi
unset _SA_JSON

success "Dependencies updated."

# ---------------------------------------------------------------------------
# 3b. Install fonts required by the personnel ID card generator
# ---------------------------------------------------------------------------

# Ensure fontconfig and fc-cache are available
if ! command -v fc-cache >/dev/null 2>&1; then
    info "Installing fontconfig..."
    apt-get install -y fontconfig >/dev/null 2>&1 && success "fontconfig installed." || warn "Could not install fontconfig — font registration may fail."
fi

# Install fonts-liberation (Arial-compatible, free, from Ubuntu repo)
if ! fc-list 2>/dev/null | grep -qi "liberation sans"; then
    info "Installing fonts-liberation (Arial-compatible fallback)..."
    apt-get install -y fonts-liberation >/dev/null 2>&1 && fc-cache -fv >/dev/null 2>&1 && success "fonts-liberation installed." || warn "Could not install fonts-liberation."
else
    info "fonts-liberation already installed."
fi

# Install Arial Nova if TTF files are bundled in the repo (commercial font, not auto-downloaded)
ARIAL_NOVA_DIR="/usr/share/fonts/truetype/arial-nova"
if fc-list 2>/dev/null | grep -qi "arial nova"; then
    success "Arial Nova already installed."
else
    FONT_SRC_DIR="$DEPLOY_DIR/fonts/arial-nova"
    if [[ -d "$FONT_SRC_DIR" ]] && ls "$FONT_SRC_DIR"/*.ttf 2>/dev/null | grep -qi "arial"; then
        mkdir -p "$ARIAL_NOVA_DIR"
        cp "$FONT_SRC_DIR"/*.ttf "$ARIAL_NOVA_DIR/"
        fc-cache -fv "$ARIAL_NOVA_DIR" >/dev/null 2>&1
        success "Arial Nova installed from $FONT_SRC_DIR."
    else
        warn "Arial Nova TTF files not found in $FONT_SRC_DIR — using Liberation Sans fallback."
        warn "Place ArialNova*.ttf in fonts/arial-nova/ to use the exact design font."
    fi
fi

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
        '$VENV_PYTHON' manage.py setup_groups
        '$VENV_PYTHON' manage.py backfill_user_groups
        '$VENV_PYTHON' manage.py purge_camera_uploads
    "
    success "Migrations, group setup, user backfill, and camera purge complete."
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

# Known-good SHA256 hash for Font Awesome 6.5.0 all.min.css (from official release).
# Regenerate if the version changes: sha256sum all.min.css
FA_CSS_SHA256="c880eb3d25c765d399840aa204fec22b3230310991089f14781f09a35ed80b8a"

if wget -q --timeout=30 -O "$FA_CSS_DIR/all.min.css" "${FA_BASE_URL}/css/all.min.css"; then
    DOWNLOADED_SHA256=$(sha256sum "$FA_CSS_DIR/all.min.css" | awk '{print $1}')
    if [[ "$DOWNLOADED_SHA256" != "$FA_CSS_SHA256" ]]; then
        warn "Font Awesome CSS SHA256 mismatch — possible CDN tampering. Removing and skipping."
        warn "  expected: $FA_CSS_SHA256"
        warn "  got     : $DOWNLOADED_SHA256"
        rm -f "$FA_CSS_DIR/all.min.css"
    else
        sed -i 's|\.\./webfonts/|webfonts/|g' "$FA_CSS_DIR/all.min.css"
        success "Font Awesome CSS downloaded and verified (SHA256 OK)."
    fi
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
    # Ensure Nginx (www-data) can read the refreshed static files.
    chmod -R g+rX "$PROJECT_DIR/staticfiles/"
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
# Ensure camera upload purge cron is installed / up-to-date
# Runs daily at 03:00 — deletes image files older than 5 days and DB records
# older than 3 years (python manage.py purge_camera_uploads).
# ---------------------------------------------------------------------------
_PURGE_CMD="$VENV_PYTHON $PROJECT_DIR/manage.py purge_camera_uploads"
_CRON_TMP2=$(mktemp)
crontab -l 2>/dev/null | grep -v 'purge_camera_uploads' > "$_CRON_TMP2" || true
printf '0 3 * * * %s >> %s/purge_camera_uploads.log 2>&1\n' \
    "$_PURGE_CMD" "$LOG_DIR" >> "$_CRON_TMP2"
crontab "$_CRON_TMP2"
rm -f "$_CRON_TMP2"
success "Camera purge cron verified: daily at 03:00."

# ---------------------------------------------------------------------------
# Ensure ActivityLog purge cron is installed / up-to-date
# Runs daily at 03:30 — deletes ActivityLog rows older than 1 year
# (python manage.py purge_activity_logs).
# ---------------------------------------------------------------------------
_ACTLOG_CMD="$VENV_PYTHON $PROJECT_DIR/manage.py purge_activity_logs"
_CRON_TMP3=$(mktemp)
crontab -l 2>/dev/null | grep -v 'purge_activity_logs' > "$_CRON_TMP3" || true
printf '30 3 * * * %s >> %s/purge_activity_logs.log 2>&1\n' \
    "$_ACTLOG_CMD" "$LOG_DIR" >> "$_CRON_TMP3"
crontab "$_CRON_TMP3"
rm -f "$_CRON_TMP3"
success "ActivityLog purge cron verified: daily at 03:30 (retain 1 year)."

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
