#!/usr/bin/env bash
# =============================================================================
# ARMGUARD RDS V1 — UFW Firewall Setup Script
# =============================================================================
# Usage:
#   sudo ./setup-firewall.sh [OPTIONS]
#
# Options:
#   --ssh-port PORT   SSH port if not 22 (default: 22)
#   --allow-lan CIDR  Allow all traffic from LAN subnet (e.g. 192.168.1.0/24)
#   --no-ipv6         Disable IPv6 rules
#   --status          Show current UFW status and exit
#   --help            Show this help
#
# This script configures UFW to:
#   - Allow SSH (port 22 or custom)
#   - Allow HTTP (port 80) for Nginx
#   - Allow HTTPS (port 443) for Nginx
#   - Block direct Gunicorn access (port 8000) from external hosts
#   - Deny everything else by default
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SSH_PORT=22
ALLOW_LAN=""
DISABLE_IPV6=false

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ssh-port)   SSH_PORT="$2"; shift 2 ;;
        --allow-lan)  ALLOW_LAN="$2"; shift 2 ;;
        --no-ipv6)    DISABLE_IPV6=true; shift ;;
        --status)
            command -v ufw &>/dev/null || die "UFW not installed."
            ufw status verbose
            exit 0 ;;
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
command -v ufw &>/dev/null || {
    info "UFW not found. Installing..."
    apt-get update -qq
    apt-get install -y ufw
}

# ---------------------------------------------------------------------------
# Disable IPv6 in UFW config if requested
# ---------------------------------------------------------------------------
if [[ "$DISABLE_IPV6" == "true" ]]; then
    sed -i 's/^IPV6=yes/IPV6=no/' /etc/default/ufw
    info "IPv6 rules disabled."
fi

# ---------------------------------------------------------------------------
# Reset and configure UFW
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}>>> Configuring UFW firewall${NC}"

# Save existing SSH session by allowing SSH before reset
# (UFW won't close existing connections on reset)
ufw --force reset

# Default policies
ufw default deny incoming
ufw default allow outgoing

# SSH — allow first to prevent lockout
if [[ "$SSH_PORT" -eq 22 ]]; then
    ufw allow 22/tcp comment "SSH"
    info "SSH allowed on port 22."
else
    ufw allow "${SSH_PORT}/tcp" comment "SSH (custom port)"
    info "SSH allowed on port $SSH_PORT."
fi

# HTTP — Nginx listens on 80 (redirects to HTTPS)
ufw allow 80/tcp comment "HTTP (Nginx → HTTPS redirect)"

# HTTPS — Nginx with SSL
ufw allow 443/tcp comment "HTTPS (Nginx)"

# mDNS — allow LAN devices to resolve armguard.local via Avahi
# UDP 5353 to multicast 224.0.0.251 is used by all mDNS clients.
# UFW default deny incoming does not block multicast by itself, so
# this explicit rule ensures avahi-daemon responses are not dropped.
ufw allow 5353/udp comment "mDNS (Avahi — armguard.local)"

# WireGuard VPN — encrypted UDP tunnel for off-LAN access
# Run scripts/setup-wireguard.sh to configure the VPN server.
ufw allow 51820/udp comment "WireGuard VPN"

# Block direct Gunicorn access from external hosts
# Gunicorn binds to 127.0.0.1:8000 so external access is already blocked
# by binding, but deny at UFW too as defence-in-depth.
ufw deny 8000/tcp comment "Block direct Gunicorn (use Nginx proxy)"

# Optional LAN-wide access (useful for admin access from trusted subnet)
if [[ -n "$ALLOW_LAN" ]]; then
    ufw allow from "$ALLOW_LAN" comment "LAN subnet full access"
    info "LAN subnet $ALLOW_LAN: all traffic allowed."
fi

# ---------------------------------------------------------------------------
# Enable UFW
# ---------------------------------------------------------------------------
echo "y" | ufw enable

success "UFW enabled."

# ---------------------------------------------------------------------------
# Display final rules
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}Current UFW status:${NC}"
ufw status verbose

# ---------------------------------------------------------------------------
# Fail2Ban — SSH and Nginx brute-force protection
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}>>> Installing Fail2Ban${NC}"

if ! command -v fail2ban-server &>/dev/null; then
    apt-get update -qq
    apt-get install -y fail2ban
fi

# Write local jail config — never edit jail.conf directly (gets overwritten on upgrades).
cat > /etc/fail2ban/jail.local <<'FAIL2BAN'
[DEFAULT]
# Ban for 1 hour after 5 failures in a 10-minute window.
bantime  = 3600
findtime = 600
maxretry = 5
backend  = systemd

# ── SSH ──────────────────────────────────────────────────────────────────────
[sshd]
enabled  = true
port     = ssh
filter   = sshd
logpath  = %(sshd_log)s
maxretry = 3
bantime  = 86400   # 24 h for SSH — more aggressive

# ── Nginx 4xx / 5xx ──────────────────────────────────────────────────────────
[nginx-http-auth]
enabled  = true
port     = http,https
filter   = nginx-http-auth
logpath  = /var/log/nginx/error.log

FAIL2BAN

# Add nginx-botsearch jail only if the filter file exists (may be absent on
# minimal Ubuntu installs). Avoids a fail2ban startup failure.
if [[ -f /etc/fail2ban/filter.d/nginx-botsearch.conf ]]; then
    cat >> /etc/fail2ban/jail.local <<'EOF_BOTSEARCH'

[nginx-botsearch]
enabled  = true
port     = http,https
filter   = nginx-botsearch
logpath  = /var/log/nginx/access.log
maxretry = 2
EOF_BOTSEARCH
    info "nginx-botsearch jail enabled."
else
    warn "nginx-botsearch filter not found — jail skipped. Install with: apt install fail2ban"
fi

systemctl enable fail2ban
systemctl restart fail2ban
success "Fail2Ban installed and configured (SSH + Nginx jails active)."

# ---------------------------------------------------------------------------
# unattended-upgrades — automatic security patches
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}>>> Configuring unattended-upgrades${NC}"

apt-get install -y unattended-upgrades apt-listchanges

# Enable automatic security updates.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT_CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT_CONF

# Restrict to security-only repos so production packages stay predictable.
sed -i 's|//\s*"${distro_id}:${distro_codename}-updates";|        "${distro_id}:${distro_codename}-updates";|' \
    /etc/apt/apt.conf.d/50unattended-upgrades 2>/dev/null || true

systemctl enable unattended-upgrades
systemctl restart unattended-upgrades
success "unattended-upgrades enabled (security patches applied automatically)."

echo
success "Firewall setup complete."
