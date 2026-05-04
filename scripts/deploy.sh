#!/usr/bin/env bash
# =============================================================================
# ARMGUARD RDS V1 — Ubuntu Server 24.04 LTS Deployment Script
# =============================================================================
# Usage:
#   ./deploy.sh [OPTIONS]
#
# Options:
#   --quick          Skip confirmation prompts (non-interactive)
#   --production     Enable full production hardening
#   --domain DOMAIN  Set the server domain/hostname
#   --lan-ip IP      Set the LAN IP address for Nginx binding
#   --static-ip IP   Configure a static LAN IP via netplan before deploying
#   --gateway IP     Gateway IP used with --static-ip (default: first 3 octets + .1)
#   --external-drive Auto-detect, format (if blank), mount and fstab-register the
#                    external backup drive at /mnt/backup
#   --help           Show this help message
#
# What this script does:
#   1. Validates OS and privileges
#   2. Installs system packages (Python, Nginx, SQLite libs, image libs)
#   3. Creates a dedicated system user 'armguard'
#   4. Clones/copies project files to /var/www/ARMGUARD_RDS_V1/
#   5. Creates Python virtual environment and installs requirements
#   6. Generates a production .env file
#   7. Downloads Font Awesome 6.5.0 locally (no CDN tracking warnings)
#   8. Runs Django migrations, setup_groups, and collectstatic
#   9. Creates and enables systemd service for Gunicorn
#  10. Installs Nginx configuration
#  11. Configures UFW firewall
#  12. Sets up log rotation
#  13. Installs database backup cron job (daily at 02:00)
#  14. Installs SSL certificate renewal cron job (monthly)
#
# Optional pre-step:
#   0. Configure static LAN IP via netplan (pass --static-ip)
#
# Optional pre-deployment step:
#   0. Configure static LAN IP via netplan (--static-ip / --gateway flags)
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_USER="armguard"
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
VENV_DIR="$DEPLOY_DIR/venv"
PROJECT_DIR="$DEPLOY_DIR/project"
LOG_DIR="/var/log/armguard"
SERVICE_NAME="armguard-gunicorn"
NGINX_CONF_NAME="armguard"
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
    local lineno=$1
    error "Deployment failed at line $lineno. Check output above."
    exit 1
}
trap 'on_error $LINENO' ERR

# ---------------------------------------------------------------------------
# LVM auto-expand: grow the root LV to use all unallocated PV space.
# Runs inside an isolated subshell with error-handling disabled so a failure
# here can never abort the main deployment.
# ---------------------------------------------------------------------------
_expand_lvm() {
    # Run the body in a subshell with set +eE so pipefail / ERR-trap
    # inheritance from the parent shell cannot kill the deploy.
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
    ) || warn "LVM expand encountered an error — deployment continues."
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
QUICK=false
PRODUCTION=false
DOMAIN=""
LAN_IP=""
STATIC_IP_SET=""
GATEWAY_SET=""
SETUP_EXT_DRIVE=false

usage() {
    grep '^#' "$0" | grep -E '^\# ' | sed 's/^# //'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick)       QUICK=true; shift ;;
        --production)  PRODUCTION=true; shift ;;
        --domain)      DOMAIN="$2"; shift 2 ;;
        --lan-ip)      LAN_IP="$2"; shift 2 ;;
        --static-ip)   STATIC_IP_SET="$2"; shift 2 ;;
        --gateway)     GATEWAY_SET="$2"; shift 2 ;;
        --external-drive) SETUP_EXT_DRIVE=true; shift ;;
        --help|-h)     usage ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
step "Pre-flight checks"

[[ $EUID -eq 0 ]] || die "This script must be run as root (use sudo)."

# OS check
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    [[ "$ID" == "ubuntu" ]] || warn "Detected OS is '$ID', not Ubuntu. Continuing anyway."
    [[ "$VERSION_ID" == "24.04" ]] || warn "Detected Ubuntu $VERSION_ID (expected 24.04). Continuing."
else
    warn "Cannot detect OS. Assuming Ubuntu 24.04."
fi

# Architecture check
ARCH="$(uname -m)"
info "Architecture: $ARCH"
[[ "$ARCH" == "x86_64" || "$ARCH" == "aarch64" ]] || warn "Unusual architecture $ARCH."

success "Pre-flight checks passed."

# ---------------------------------------------------------------------------
# LVM expand — maximise available disk space before doing anything else
# ---------------------------------------------------------------------------
_expand_lvm

# ---------------------------------------------------------------------------
# Interactive configuration (skipped with --quick)
# ---------------------------------------------------------------------------
if [[ "$QUICK" == "false" ]]; then
    step "Configuration"

    if [[ -z "$DOMAIN" ]]; then
        read -rp "  Server domain or IP (e.g. armguard.local or 192.168.1.100): " DOMAIN
        [[ -n "$DOMAIN" ]] || die "Domain/IP is required."
    fi

    if [[ -z "$LAN_IP" ]]; then
        DEFAULT_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || echo "")
        read -rp "  LAN IP address [${DEFAULT_IP:-auto}]: " LAN_IP
        LAN_IP="${LAN_IP:-$DEFAULT_IP}"
    fi

    echo
    echo "  Deployment summary:"
    echo "    Domain/IP  : $DOMAIN"
    echo "    LAN IP     : $LAN_IP"
    echo "    Deploy dir : $DEPLOY_DIR"
    echo "    System user: $DEPLOY_USER"
    echo
    read -rp "  Proceed? [y/N] " CONFIRM
    [[ "$CONFIRM" =~ ^[Yy]$ ]] || { info "Aborted by user."; exit 0; }
else
    # --quick mode: derive defaults
    [[ -z "$DOMAIN" ]] && DOMAIN=$(hostname -I | awk '{print $1}') && info "Domain defaulting to $DOMAIN"
    [[ -z "$LAN_IP" ]] && LAN_IP="$DOMAIN"
fi

# ---------------------------------------------------------------------------
# 0. Static IP configuration (optional — triggered by --static-ip)
# ---------------------------------------------------------------------------
if [[ -n "${STATIC_IP_SET:-}" ]]; then
    step "Configuring static LAN IP: $STATIC_IP_SET"
    STATIC_IP_SCRIPT="$SCRIPT_DIR/set-static-ip.sh"
    if [[ ! -f "$STATIC_IP_SCRIPT" ]]; then
        die "set-static-ip.sh not found at $STATIC_IP_SCRIPT"
    fi
    STATIC_IP_ARGS=("--ip" "$STATIC_IP_SET")
    if [[ -n "${GATEWAY_SET:-}" ]]; then
        STATIC_IP_ARGS+=("--gateway" "$GATEWAY_SET")
    else
        # Derive gateway: replace last octet with 1 (e.g. 192.168.0.11 → 192.168.0.1)
        AUTO_GW=$(echo "$STATIC_IP_SET" | awk -F. '{printf "%s.%s.%s.1", $1,$2,$3}')
        info "Gateway not specified — defaulting to $AUTO_GW"
        STATIC_IP_ARGS+=("--gateway" "$AUTO_GW")
    fi
    bash "$STATIC_IP_SCRIPT" "${STATIC_IP_ARGS[@]}"
    success "Static IP configured. Continuing deployment…"
fi

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
step "Installing system packages"

apt-get update -qq

PACKAGES=(
    python3.12 python3.12-venv python3.12-dev
    python3-pip
    build-essential
    libsqlite3-dev
    libjpeg-dev zlib1g-dev libtiff-dev libfreetype6-dev
    liblcms2-dev libwebp-dev libharfbuzz-dev libfribidi-dev
    libmupdf-dev mupdf-tools
    nginx
    git curl wget unzip
    logrotate
    ufw
    avahi-daemon libnss-mdns
)

apt-get install -y --no-install-recommends "${PACKAGES[@]}" \
    | grep -E "^(Setting up|Already installed)" || true

success "System packages installed."

# ---------------------------------------------------------------------------
# 1b. Avahi mDNS — enable armguard.local hostname resolution on LAN
# ---------------------------------------------------------------------------
step "Configuring Avahi mDNS (armguard.local)"

MDNS_HOSTNAME="armguard"
hostnamectl set-hostname "$MDNS_HOSTNAME"
info "Hostname set to: $MDNS_HOSTNAME (broadcasts as ${MDNS_HOSTNAME}.local via mDNS)"

# Write a hardened avahi config — disable OS fingerprinting, workstation
# advertisement, wide-area DNS-SD, and IPv6 multicast (LAN-only deployment).
mkdir -p /etc/avahi
cp "$SCRIPT_DIR/avahi-daemon.conf" /etc/avahi/avahi-daemon.conf

systemctl enable avahi-daemon
systemctl restart avahi-daemon
success "Avahi started — server reachable as ${MDNS_HOSTNAME}.local on the LAN."

# ---------------------------------------------------------------------------
# 1c. Generate self-signed SSL certificate (IP + armguard.local DNS SAN)
# ---------------------------------------------------------------------------
step "Generating self-signed SSL certificate"

SSL_CERT="/etc/ssl/certs/armguard-selfsigned.crt"
SSL_KEY="/etc/ssl/private/armguard-selfsigned.key"
DH_PARAM="/etc/ssl/certs/dhparam.pem"
SSL_YEAR=$(date +%Y)

if [[ ! -f "$SSL_CERT" ]]; then
    openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
        -keyout "$SSL_KEY" \
        -out    "$SSL_CERT" \
        -subj   "/C=PH/ST=Metro Manila/L=Manila/O=ArmGuard RDS ${SSL_YEAR}/OU=Security/CN=${MDNS_HOSTNAME}.local" \
        -addext "subjectAltName=IP:${LAN_IP},DNS:${MDNS_HOSTNAME}.local"
    chmod 644 "$SSL_CERT"
    chmod 600 "$SSL_KEY"
    success "SSL certificate generated (CN=${MDNS_HOSTNAME}.local, SAN: IP:${LAN_IP} + DNS:${MDNS_HOSTNAME}.local)"
else
    info "SSL certificate already exists at $SSL_CERT — skipping generation."
fi

if [[ ! -f "$DH_PARAM" ]]; then
    info "Generating DH parameters (~30–60 s)…"
    openssl dhparam -out "$DH_PARAM" 2048
    success "DH parameters generated."
else
    info "DH parameters already exist at $DH_PARAM — skipping."
fi

# ---------------------------------------------------------------------------
# 2. Create system user
# ---------------------------------------------------------------------------
step "Creating system user '$DEPLOY_USER'"

if id "$DEPLOY_USER" &>/dev/null; then
    info "User '$DEPLOY_USER' already exists."
else
    useradd --system --shell /bin/bash --home-dir "$DEPLOY_DIR" \
            --create-home "$DEPLOY_USER"
    success "User '$DEPLOY_USER' created."
fi

# ---------------------------------------------------------------------------
# 3. Create directory structure
# ---------------------------------------------------------------------------
step "Creating deployment directories"

mkdir -p "$DEPLOY_DIR"/{project,venv,backups}
mkdir -p "$LOG_DIR"
# FileBasedCache directory — shared by all Gunicorn workers (see CACHES in base.py).
mkdir -p "$DEPLOY_DIR/cache"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR" "$LOG_DIR"
chmod 750 "$DEPLOY_DIR"
chmod 750 "$DEPLOY_DIR/cache"
# Allow Nginx (www-data) to read static/media files inside the deploy dir.
# www-data is added to the armguard group so it inherits the group r-x
# permission on DEPLOY_DIR (750) and can traverse into project/staticfiles/.
usermod -aG "$DEPLOY_USER" www-data
success "Directories created."

# ---------------------------------------------------------------------------
# 4. Copy project files
# ---------------------------------------------------------------------------
step "Copying project files to $DEPLOY_DIR"

if [[ -d "$PROJECT_ROOT/project" ]]; then
    rsync -a --exclude='__pycache__' --exclude='*.pyc' \
              --exclude='.git' --exclude='venv' \
              --exclude='*.db' --exclude='backups' \
              --exclude='logs' --exclude='staticfiles' \
              --exclude='media' \
              "$PROJECT_ROOT/project/" "$PROJECT_DIR/"
    rsync -a --exclude='.git' \
              "$PROJECT_ROOT/requirements.txt" "$DEPLOY_DIR/"
    # Copy scripts/ so gunicorn.conf.py and other runtime scripts are available
    # at $DEPLOY_DIR/scripts/ (the systemd unit references gunicorn.conf.py there).
    if [[ -d "$PROJECT_ROOT/scripts" ]]; then
        mkdir -p "$DEPLOY_DIR/scripts"
        rsync -a --exclude='.git' \
                  "$PROJECT_ROOT/scripts/" "$DEPLOY_DIR/scripts/"
    fi
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR"
    success "Project files copied."
else
    warn "Source project dir not found at $PROJECT_ROOT/project"
    warn "Copy your project files to $PROJECT_DIR manually, then re-run --quick."
    info "Creating placeholder requirements.txt..."
    cat > "$DEPLOY_DIR/requirements.txt" <<'EOF'
Django==6.0.3
gunicorn==22.0.0
whitenoise==6.12.0
python-dotenv==1.2.2
pillow==12.1.1
PyMuPDF==1.27.1
qrcode==8.2
djangorestframework==3.16.0
django-otp==1.7.0
gspread>=6.0.0
google-auth>=2.29.0
EOF
fi

# ---------------------------------------------------------------------------
# 5. Python virtual environment
# ---------------------------------------------------------------------------
step "Setting up Python virtual environment"

if [[ ! -f "$VENV_DIR/bin/python" ]]; then
    sudo -u "$DEPLOY_USER" python3.12 -m venv "$VENV_DIR"
    success "Virtual environment created."
fi

VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python"

sudo -u "$DEPLOY_USER" "$VENV_PIP" install --upgrade pip --quiet
sudo -u "$DEPLOY_USER" "$VENV_PIP" install -r "$DEPLOY_DIR/requirements.txt" --quiet

# Ensure gunicorn is installed (may not be in requirements.txt yet)
sudo -u "$DEPLOY_USER" "$VENV_PIP" install gunicorn --quiet

success "Python dependencies installed."

# ---------------------------------------------------------------------------
# 6. Generate .env file
# ---------------------------------------------------------------------------
step "Generating production .env file"

ENV_FILE="$DEPLOY_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    info ".env already exists — skipping generation. Edit manually if needed."
    # When re-deploying to a different server/IP, ensure this server's hosts are in ALLOWED_HOSTS.
    # Missing entries cause Django to return 400 Bad Request for every request.
    if grep -q "^DJANGO_ALLOWED_HOSTS=" "$ENV_FILE"; then
        _current_hosts=$(grep "^DJANGO_ALLOWED_HOSTS=" "$ENV_FILE" | cut -d= -f2-)
        _updated_hosts="$_current_hosts"
        for _host in "$DOMAIN" "$LAN_IP"; do
            if [[ -n "$_host" ]] && ! echo "$_updated_hosts" | grep -qE "(^|,)${_host}(,|$)"; then
                _updated_hosts="${_updated_hosts},${_host}"
                info "Adding '$_host' to ALLOWED_HOSTS."
            fi
        done
        if [[ "$_updated_hosts" != "$_current_hosts" ]]; then
            sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${_updated_hosts}|" "$ENV_FILE"
            success "ALLOWED_HOSTS updated in existing .env: ${_updated_hosts}"
        else
            info "ALLOWED_HOSTS already contains all required hosts."
        fi
        unset _current_hosts _updated_hosts _host
    fi
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")

    cat > "$ENV_FILE" <<EOF
# ARMGUARD RDS V1 — Production Environment
# Generated: $TIMESTAMP
# IMPORTANT: Keep this file secret. Never commit to version control.

# Django core
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$DOMAIN,$LAN_IP,armguard.local,localhost,127.0.0.1

# Custom admin URL (change this to something not guessable)
DJANGO_ADMIN_URL=secure-admin-$(python3 -c "import secrets; print(secrets.token_hex(4))")

# Database (SQLite for V1 — paths relative to project dir)
# DB_ENGINE=django.db.backends.sqlite3
# DB_NAME=/var/www/ARMGUARD_RDS_V1/project/db.sqlite3

# Security
# Keep the three SECURE_* flags False until SSL is installed and certbot has run.
# After SSL is confirmed working:
#   1. Set SECURE_SSL_REDIRECT=True
#   2. Set SESSION_COOKIE_SECURE=True
#   3. Set CSRF_COOKIE_SECURE=True
#   4. sudo systemctl restart armguard-gunicorn
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_HSTS_SECONDS=31536000
CSRF_TRUSTED_ORIGINS=https://$DOMAIN,https://armguard.local,https://$LAN_IP
# SSL certificate path (used by the in-app cert download + notification feature)
# Default is correct for standard deploy; override only if cert lives elsewhere.
SSL_CERT_PATH=/etc/ssl/certs/armguard-selfsigned.crt

# Google Sheets import (optional)
# Set this to the absolute path of your service-account JSON key file.
# The service-account email must have Viewer access to each sheet you import.
# Leave blank to disable the Google Sheets import tab on /personnel/import/.
# GOOGLE_SA_JSON=/var/www/armguard-sa.json

# Gunicorn (if tuning via env vars)
# GUNICORN_WORKERS=2
# GUNICORN_TIMEOUT=60
EOF

    chown "$DEPLOY_USER:$DEPLOY_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    success ".env file generated at $ENV_FILE"
    warn "Review $ENV_FILE and update settings before starting the service."
fi

# ---------------------------------------------------------------------------
# 7. Download Font Awesome locally (eliminates CDN tracking-prevention warning)
# ---------------------------------------------------------------------------
step "Downloading Font Awesome 6.5.0 to local static files"

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

# Known-good SHA256 hashes for Font Awesome 6.5.0 (from official release)
# Regenerate if you upgrade the version: sha256sum all.min.css
FA_CSS_SHA256="c880eb3d25c765d399840aa204fec22b3230310991089f14781f09a35ed80b8a"

# Download CSS and rewrite ../webfonts/ -> webfonts/ so it resolves correctly
if wget -q --timeout=30 -O "$FA_CSS_DIR/all.min.css" "${FA_BASE_URL}/css/all.min.css"; then
    # Verify SHA256 before using the file — guards against CDN tampering.
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

# Download webfonts
FA_FONT_FAILURES=0
for font in "${FA_WEBFONTS[@]}"; do
    if ! wget -q --timeout=30 -O "$FA_WEBFONTS_DIR/$font" "${FA_BASE_URL}/webfonts/${font}"; then
        warn "Failed to download webfont: $font"
        FA_FONT_FAILURES=$((FA_FONT_FAILURES + 1))
    fi
done

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$FA_CSS_DIR"

if [[ "$FA_FONT_FAILURES" -eq 0 ]]; then
    success "All Font Awesome webfonts downloaded."
else
    warn "$FA_FONT_FAILURES webfont(s) failed. Run the update script later to retry."
fi

# ---------------------------------------------------------------------------
# 8. Django migrations and static files
# ---------------------------------------------------------------------------
step "Running Django setup (migrate + collectstatic)"

MANAGE="$VENV_PYTHON $PROJECT_DIR/manage.py"
DJANGO_ENV="DJANGO_SETTINGS_MODULE=armguard.settings.production"

# Source env vars for manage.py calls
set -a
# shellcheck source=/dev/null
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
set +a

export DJANGO_SETTINGS_MODULE=armguard.settings.production

sudo -u "$DEPLOY_USER" bash -c "
    source '$ENV_FILE' 2>/dev/null || true
    export DJANGO_SETTINGS_MODULE=armguard.settings.production
    cd '$PROJECT_DIR'
    '$VENV_PYTHON' manage.py collectstatic --noinput --clear
    '$VENV_PYTHON' manage.py migrate --noinput
    '$VENV_PYTHON' manage.py setup_groups
    '$VENV_PYTHON' manage.py backfill_user_groups
"

# Ensure Nginx (www-data, now in the armguard group) can read all static files.
chmod -R g+rX "$PROJECT_DIR/staticfiles/"
success "Migrations applied, groups created, users backfilled, and static files collected."

# ---------------------------------------------------------------------------
# 8. Systemd service
# ---------------------------------------------------------------------------
step "Installing systemd service"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ -f "$SCRIPT_DIR/armguard-gunicorn.service" ]]; then
    # Use the provided template, substitute paths
    sed "s|__DEPLOY_DIR__|$DEPLOY_DIR|g; s|__PROJECT_DIR__|$PROJECT_DIR|g; \
         s|__VENV_DIR__|$VENV_DIR|g; s|__DEPLOY_USER__|$DEPLOY_USER|g" \
        "$SCRIPT_DIR/armguard-gunicorn.service" > "$SERVICE_FILE"
else
    # Inline fallback
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ArmGuard RDS V1 — Gunicorn Application Server
After=network.target
Documentation=https://docs.djangoproject.com

[Service]
Type=notify
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$ENV_FILE
Environment=GUNICORN_WORKERS=3
Environment=GUNICORN_THREADS=2
EnvironmentFile=-/etc/gunicorn/workers.env
Environment=DJANGO_SETTINGS_MODULE=armguard.settings.production
ExecStart=$VENV_DIR/bin/gunicorn armguard.wsgi:application \\
    --bind 127.0.0.1:8000 \\
    --workers \$GUNICORN_WORKERS \\
    --worker-class gthread \\
    --threads \$GUNICORN_THREADS \\
    --timeout 120 \\
    --max-requests 1000 \\
    --max-requests-jitter 100 \\
    --log-file $LOG_DIR/gunicorn.log \\
    --access-logfile $LOG_DIR/gunicorn-access.log \\
    --capture-output
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=30
PrivateTmp=true
NoNewPrivileges=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$LOG_DIR $DEPLOY_DIR

[Install]
WantedBy=multi-user.target
EOF
fi

chmod 644 "$SERVICE_FILE"
systemctl daemon-reload

# Install gunicorn-autoconf.sh so it runs on every future update
if [[ -f "$SCRIPT_DIR/gunicorn-autoconf.sh" ]]; then
    install -m 755 "$SCRIPT_DIR/gunicorn-autoconf.sh" /usr/local/bin/gunicorn-autoconf.sh
    info "Installed gunicorn-autoconf.sh to /usr/local/bin/"
fi

# Compute workers before first start
if [[ -x "/usr/local/bin/gunicorn-autoconf.sh" ]]; then
    bash /usr/local/bin/gunicorn-autoconf.sh
    success "Initial Gunicorn worker count computed."
fi

systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
success "Service '$SERVICE_NAME' installed and started."

# ---------------------------------------------------------------------------
# 9. Nginx configuration
# ---------------------------------------------------------------------------
step "Configuring Nginx"

NGINX_AVAILABLE="/etc/nginx/sites-available/$NGINX_CONF_NAME"
NGINX_ENABLED="/etc/nginx/sites-enabled/$NGINX_CONF_NAME"

# Collect staticfiles path
STATIC_ROOT="$PROJECT_DIR/staticfiles"
MEDIA_ROOT="$PROJECT_DIR/media"

if [[ -f "$NGINX_AVAILABLE" ]]; then
    info "Nginx config already exists at $NGINX_AVAILABLE — skipping (preserves SSL config)."
    info "To reset it: sudo rm $NGINX_AVAILABLE && sudo bash scripts/deploy.sh ..."
elif [[ -f "$SCRIPT_DIR/nginx-armguard.conf" ]]; then
    sed "s|__DOMAIN__|$DOMAIN|g; s|__LAN_IP__|$LAN_IP|g; \
         s|__STATIC_ROOT__|$STATIC_ROOT|g; \
         s|__MEDIA_ROOT__|$MEDIA_ROOT|g" \
        "$SCRIPT_DIR/nginx-armguard.conf" > "$NGINX_AVAILABLE"
else
    # Inline HTTP-only fallback (no SSL)
    cat > "$NGINX_AVAILABLE" <<EOF
# ArmGuard RDS V1 — Nginx Configuration (HTTP only, no SSL)
# For SSL, obtain a certificate and edit this file.

server {
    listen 80;
    server_name $DOMAIN $LAN_IP;

    client_max_body_size 20M;

    # Gzip compression — cuts HTML/JSON transfer size ~70 % on a LAN.
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml text/javascript
               application/x-font-ttf font/opentype image/svg+xml;

    # Rate limit login endpoint
    limit_req_zone \$binary_remote_addr zone=login_zone:10m rate=5r/m;

    location /static/ {
        alias $STATIC_ROOT/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias $MEDIA_ROOT/;
        expires 7d;
    }

    location /accounts/login/ {
        limit_req zone=login_zone burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
EOF
fi

ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
rm -f /etc/nginx/sites-enabled/default

# Create the proxy-params snippet required by nginx-armguard.conf.
# nginx -t will fail if this file is missing.
PROXY_PARAMS="/etc/nginx/snippets/proxy-params.conf"
if [[ ! -f "$PROXY_PARAMS" ]]; then
    mkdir -p /etc/nginx/snippets
    cat > "$PROXY_PARAMS" <<'EOF'
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_redirect    off;
# HTTP/1.1 + clear Connection header: required for Nginx upstream keepalive.
# Without these, Nginx uses HTTP/1.0 and closes the backend connection after
# every request, negating the keepalive 8 pool in the upstream block.
proxy_http_version 1.1;
proxy_set_header   Connection "";
# Buffering ON: Nginx absorbs the full Gunicorn response immediately, freeing
# the sync worker for the next request.  Nginx then streams to the client at
# its own pace.  'off' ties up workers waiting for slow clients to read.
proxy_buffering         on;
proxy_buffer_size       8k;
proxy_buffers           8 16k;
proxy_busy_buffers_size 32k;
EOF
    info "Created $PROXY_PARAMS"
fi

nginx -t && systemctl reload nginx
success "Nginx configured."

# ---------------------------------------------------------------------------
# 10. Firewall
# ---------------------------------------------------------------------------
step "Configuring UFW firewall"

if command -v ufw &>/dev/null; then
    if [[ -f "$SCRIPT_DIR/setup-firewall.sh" ]]; then
        bash "$SCRIPT_DIR/setup-firewall.sh"
    else
        ufw --force reset
        ufw default deny incoming
        ufw default allow outgoing
        ufw allow 22/tcp comment "SSH"
        ufw allow 80/tcp comment "HTTP"
        ufw allow 443/tcp comment "HTTPS"
        ufw deny 8000/tcp comment "Block direct Gunicorn access"
        echo "y" | ufw enable
    fi
    success "UFW firewall configured."
else
    warn "UFW not found. Configure firewall manually."
fi

# ---------------------------------------------------------------------------
# 11. Log rotation
# ---------------------------------------------------------------------------
step "Setting up log rotation"

cat > /etc/logrotate.d/armguard <<EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    sharedscripts
    postrotate
        systemctl reload $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}
EOF

success "Log rotation configured."

# ---------------------------------------------------------------------------
# 12. Backup cron job
# ---------------------------------------------------------------------------
step "Installing backup cron job"

CRON_SCRIPT="$DEPLOY_DIR/scripts/db-backup-cron.sh"
if [[ -f "$SCRIPT_DIR/db-backup-cron.sh" ]]; then
    mkdir -p "$DEPLOY_DIR/scripts"
    [[ "$(realpath "$SCRIPT_DIR/db-backup-cron.sh")" != "$(realpath "$CRON_SCRIPT")" ]] && \
        cp "$SCRIPT_DIR/db-backup-cron.sh" "$CRON_SCRIPT"
    chmod +x "$CRON_SCRIPT"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$CRON_SCRIPT"

    # Install cron for armguard user (daily at 02:00)
    # Use a temp file — avoids crontab -l's non-zero exit (no existing crontab)
    # from propagating through set -Eo pipefail and firing on_error.
    _CRON_TMP=$(mktemp)
    crontab -u "$DEPLOY_USER" -l 2>/dev/null | grep -v "$CRON_SCRIPT" > "$_CRON_TMP" || true
    printf '0 2 * * * %s >> %s/backup.log 2>&1\n' "$CRON_SCRIPT" "$LOG_DIR" >> "$_CRON_TMP"
    crontab -u "$DEPLOY_USER" "$_CRON_TMP"
    rm -f "$_CRON_TMP"
    success "Daily backup cron job installed (02:00 AM)."
else
    warn "db-backup-cron.sh not found in scripts/; backup cron not installed."
fi

# Install consolidated backup.sh cron (every 3 hours, low CPU+I/O priority).
# Runs as root — backup.sh requires root to write /var/backups/armguard and
# sync to the external drive at /mnt/backup.
BACKUP_SH_DEPLOY="$DEPLOY_DIR/scripts/backup.sh"
if [[ -f "$SCRIPT_DIR/backup.sh" ]]; then
    mkdir -p "$DEPLOY_DIR/scripts"
    [[ "$(realpath "$SCRIPT_DIR/backup.sh")" != "$(realpath "$BACKUP_SH_DEPLOY")" ]] && \
        cp "$SCRIPT_DIR/backup.sh" "$BACKUP_SH_DEPLOY"
    chmod +x "$BACKUP_SH_DEPLOY"
    # Use a temp file — avoids crontab -l's non-zero exit (no existing crontab)
    # from propagating through set -Eo pipefail and firing on_error.
    _CRON_TMP=$(mktemp)
    crontab -l 2>/dev/null | grep -v 'backup.sh' > "$_CRON_TMP" || true
    printf '0 */3 * * * nice -n 19 ionice -c 3 %s >> %s/backup.log 2>&1\n' \
        "$BACKUP_SH_DEPLOY" "$LOG_DIR" >> "$_CRON_TMP"
    crontab "$_CRON_TMP"
    rm -f "$_CRON_TMP"
    success "Every-3-hour consolidated backup cron installed (nice -n 19 ionice -c 3)."
else
    warn "backup.sh not found in scripts/; consolidated backup cron not installed."
fi

# ---------------------------------------------------------------------------
# 12b. External backup drive setup (only when --external-drive is passed)
# ---------------------------------------------------------------------------
_setup_external_drive() {
    local mount_point="/mnt/backup"
    local chosen_dev chosen_uuid chosen_fs

    step "External backup drive setup"

    # List all unmounted block devices that are NOT the root disk
    local root_disk
    root_disk=$(lsblk -no PKNAME "$(findmnt -n -o SOURCE /)" 2>/dev/null | head -1)

    info "Scanning for external drives (excluding root disk: /dev/${root_disk:-unknown})…"
    echo

    # Build candidate list: whole disks and partitions that are NOT the root disk
    local candidates=() labels=()
    while IFS= read -r line; do
        local dev size type fstype label
        dev=$(echo "$line"   | awk '{print $1}')
        size=$(echo "$line"  | awk '{print $2}')
        type=$(echo "$line"  | awk '{print $3}')
        fstype=$(echo "$line"| awk '{print $4}')
        label=$(echo "$line" | awk '{print $5}')
        # Skip root disk and its children
        [[ "/dev/$dev" == "/dev/${root_disk}"* ]] && continue
        # Skip loop, rom, ram devices
        [[ "$type" == "loop" || "$type" == "rom" || "$type" == "ram" ]] && continue
        # Skip devices that are already mounted
        mountpoint -q "/dev/$dev" 2>/dev/null && continue
        candidates+=("$dev")
        labels+=("$size ${fstype:-unformatted} ${label}")
    done < <(lsblk -rno NAME,SIZE,TYPE,FSTYPE,LABEL 2>/dev/null)

    if [[ ${#candidates[@]} -eq 0 ]]; then
        warn "No candidate external drives found. Plug in the drive and re-run with --external-drive."
        return 0
    fi

    echo -e "  ${BOLD}Available drives:${NC}"
    local i
    for i in "${!candidates[@]}"; do
        printf "  [%d] /dev/%s  (%s)\n" "$((i+1))" "${candidates[$i]}" "${labels[$i]}"
    done
    echo "  [0] Skip — do not configure external drive"
    echo

    local choice
    read -rp "  Select drive number: " choice
    if [[ "$choice" == "0" || -z "$choice" ]]; then
        info "External drive setup skipped."
        return 0
    fi
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 || "$choice" -gt ${#candidates[@]} ]]; then
        warn "Invalid selection — external drive setup skipped."
        return 0
    fi

    chosen_dev="/dev/${candidates[$((choice-1))]}"
    info "Selected: $chosen_dev"

    # Detect existing filesystem
    chosen_fs=$(blkid -o value -s TYPE "$chosen_dev" 2>/dev/null || true)

    if [[ -z "$chosen_fs" ]]; then
        # No filesystem — offer to format as ext4
        echo
        warn "$chosen_dev has no filesystem. Formatting will ERASE ALL DATA on the drive."
        local confirm
        read -rp "  Format $chosen_dev as ext4 for backup storage? [yes/N]: " confirm
        if [[ "${confirm,,}" != "yes" ]]; then
            info "Format declined — external drive setup skipped."
            return 0
        fi
        info "Formatting $chosen_dev as ext4 with label ARMGUARD_BCK …"
        mkfs.ext4 -L ARMGUARD_BCK -F "$chosen_dev"
        chosen_fs="ext4"
        success "Formatted: $chosen_dev (ext4, label ARMGUARD_BCK)"
    else
        info "Detected existing filesystem: $chosen_fs"
        if [[ "$chosen_fs" != "ext4" && "$chosen_fs" != "xfs" && "$chosen_fs" != "btrfs" ]]; then
            warn "Filesystem '$chosen_fs' may not be optimal for backups. Proceeding anyway."
        fi
    fi

    # Retrieve UUID (post-format or pre-existing)
    chosen_uuid=$(blkid -o value -s UUID "$chosen_dev" 2>/dev/null || true)
    if [[ -z "$chosen_uuid" ]]; then
        warn "Could not read UUID from $chosen_dev — skipping fstab entry."
        return 0
    fi
    info "UUID: $chosen_uuid"

    # Create mount point
    mkdir -p "$mount_point"
    chmod 750 "$mount_point"

    # Check if already in fstab
    if grep -q "$chosen_uuid" /etc/fstab 2>/dev/null; then
        info "UUID already present in /etc/fstab — skipping duplicate entry."
    else
        local fstab_line
        if [[ "$chosen_fs" == "ext4" ]]; then
            fstab_line="UUID=$chosen_uuid $mount_point ext4 defaults,nofail,noatime 0 2"
        elif [[ "$chosen_fs" == "xfs" ]]; then
            fstab_line="UUID=$chosen_uuid $mount_point xfs  defaults,nofail,noatime 0 2"
        else
            fstab_line="UUID=$chosen_uuid $mount_point $chosen_fs defaults,nofail 0 2"
        fi
        # Back up fstab before modifying
        cp /etc/fstab /etc/fstab.bak."$TIMESTAMP"
        echo "$fstab_line" >> /etc/fstab
        success "fstab entry added: $fstab_line"
        info "Original fstab backed up to /etc/fstab.bak.$TIMESTAMP"
    fi

    # Mount now
    if mountpoint -q "$mount_point" 2>/dev/null; then
        info "$mount_point is already mounted."
    else
        mount "$chosen_dev" "$mount_point" && success "Mounted $chosen_dev at $mount_point" \
            || warn "Mount failed — check device and filesystem. fstab entry was still written."
    fi

    # Update backup.sh to use the confirmed UUID (replace the placeholder)
    if [[ -f "$BACKUP_SH_DEPLOY" ]]; then
        sed -i "s|UUID=\"ff28a2b1-df2f-402b-9b88-38133225a40f\"|UUID=\"$chosen_uuid\"|g" \
            "$BACKUP_SH_DEPLOY" 2>/dev/null || true
        info "backup.sh updated with UUID $chosen_uuid"
    fi

    # Create the armguard subdirectory on the external drive
    mkdir -p "$mount_point/armguard"
    success "External backup drive configured: $chosen_dev → $mount_point (UUID $chosen_uuid)"
}

if [[ "$SETUP_EXT_DRIVE" == "true" ]]; then
    _setup_external_drive
else
    info "Tip: re-run with --external-drive to auto-configure an external backup drive."
fi

# ---------------------------------------------------------------------------
# 13. SSL certificate renewal cron job (monthly, runs as root)
# ---------------------------------------------------------------------------
step "Installing SSL certificate renewal cron job"

RENEW_SCRIPT="$DEPLOY_DIR/scripts/renew-ssl-cert.sh"
if [[ -f "$SCRIPT_DIR/renew-ssl-cert.sh" ]]; then
    mkdir -p "$DEPLOY_DIR/scripts"
    [[ "$(realpath "$SCRIPT_DIR/renew-ssl-cert.sh")" != "$(realpath "$RENEW_SCRIPT")" ]] && \
        cp "$SCRIPT_DIR/renew-ssl-cert.sh" "$RENEW_SCRIPT"
    chmod +x "$RENEW_SCRIPT"
    # Cron runs as root (cert/nginx ops require root privileges).
    # Checks on the 1st of every month at 03:00 AM; renews only if expiry < 45 days away.
    _CRON_TMP=$(mktemp)
    crontab -l 2>/dev/null | grep -v "$RENEW_SCRIPT" > "$_CRON_TMP" || true
    printf '0 3 1 * * %s >> %s/ssl-renewal.log 2>&1\n' "$RENEW_SCRIPT" "$LOG_DIR" >> "$_CRON_TMP"
    crontab "$_CRON_TMP"
    rm -f "$_CRON_TMP"
    success "Monthly SSL renewal cron installed (3:00 AM on 1st of each month)."
else
    warn "renew-ssl-cert.sh not found in scripts/; SSL renewal cron not installed."
fi

# ---------------------------------------------------------------------------
# Post-deployment check
# ---------------------------------------------------------------------------
step "Post-deployment verification"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    success "Gunicorn service is running."
else
    error "Gunicorn service is NOT running. Check: journalctl -u $SERVICE_NAME -n 50"
fi

if systemctl is-active --quiet nginx; then
    success "Nginx is running."
else
    error "Nginx is NOT running. Check: journalctl -u nginx -n 20"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║        ARMGUARD RDS V1 — Deployment Complete             ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo
echo -e "  Application URL   : https://armguard.local  (also https://${LAN_IP})"
  echo -e "  Deploy directory  : $DEPLOY_DIR"
  echo -e "  Logs              : $LOG_DIR"
  echo -e "  .env file         : $ENV_FILE"
  echo -e "  Systemd service   : $SERVICE_NAME"
echo
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Review .env at $ENV_FILE"
echo -e "  2. Create a superuser:"
echo -e "     sudo -u $DEPLOY_USER $VENV_PYTHON $PROJECT_DIR/manage.py createsuperuser"
echo -e "  3. Install the SSL cert on each client device so the browser trusts it:"
echo -e "     Download from https://armguard.local/download/ssl-cert/ and install as"
echo -e "     Trusted Root CA (see scripts/SSL_SELFSIGNED.md, Section 8)"
echo -e "  4. Enable SECURE_SSL_REDIRECT in .env once SSL is confirmed working"
echo -e "     (copy the nginx-armguard-ssl-lan.conf to /etc/nginx/sites-available/armguard)"
echo
