#!/usr/bin/env bash
# =============================================================================
# ARMGUARD RDS V1 — WireGuard VPN Setup
# =============================================================================
# Sets up a WireGuard VPN server on the ArmGuard machine so devices that are
# not on the LAN can still securely access the app (e.g. officers on a
# separate network, remote administrators).
#
# After running this script:
#   • WireGuard listens on 0.0.0.0:51820 (UDP)
#   • Server VPN IP    → 10.8.0.1
#   • First peer conf  → /etc/wireguard/peers/peer1.conf
#   • SSL cert regenerated with 10.8.0.1 as an IP SAN
#   • Django ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS updated in .env
#   • WireGuard clients reach the app at https://10.8.0.1
#
# To add more peers later:
#   sudo bash scripts/add-wireguard-peer.sh [--name laptop]
#
# Usage:
#   sudo bash scripts/setup-wireguard.sh [OPTIONS]
#
# Options:
#   --server-ip IP     IP (or DNS name) clients use to reach this machine.
#                      LAN access  → use the server LAN IP (default: 192.168.0.11)
#                      Remote access → use the public IP / FQDN instead
#   --wg-port PORT     WireGuard listen port            (default: 51820)
#   --wg-subnet CIDR   WireGuard IP subnet              (default: 10.8.0.0/24)
#   --wg-ip IP         WireGuard IP assigned to server  (default: 10.8.0.1)
#   --no-ssl-regen     Skip SSL certificate regeneration
#   --no-first-peer    Skip generating an initial peer config
#   --help             Show this help
# =============================================================================

set -Eeo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
ENV_FILE="$DEPLOY_DIR/.env"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SERVER_IP="192.168.0.11"       # LAN IP — override with public IP for remote access
WG_PORT=51820
WG_SUBNET="10.8.0.0/24"
WG_SERVER_IP="10.8.0.1"
REGEN_SSL=true
MAKE_FIRST_PEER=true
MDNS_HOST="armguard.local"
CERT="/etc/ssl/certs/armguard-selfsigned.crt"
KEY="/etc/ssl/private/armguard-selfsigned.key"
PEERS_DIR="/etc/wireguard/peers"
WG_CONF="/etc/wireguard/wg0.conf"

# ---------------------------------------------------------------------------
# Colour helpers  (matches style used across other scripts in this repo)
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }
step()    { echo -e "\n${BOLD}>>> $*${NC}"; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --server-ip)    SERVER_IP="$2";     shift 2 ;;
        --wg-port)      WG_PORT="$2";       shift 2 ;;
        --wg-subnet)    WG_SUBNET="$2";     shift 2 ;;
        --wg-ip)        WG_SERVER_IP="$2";  shift 2 ;;
        --no-ssl-regen) REGEN_SSL=false;    shift   ;;
        --no-first-peer) MAKE_FIRST_PEER=false; shift ;;
        --help|-h)
            grep '^#' "$0" | grep -E '^\# ' | sed 's/^# //'
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root: sudo $0"

if [[ -f "$WG_CONF" ]]; then
    die "WireGuard is already configured at $WG_CONF.
       Use 'sudo wg show' to inspect it.
       To start over, remove $WG_CONF and re-run this script."
fi

# ---------------------------------------------------------------------------
# 1. Install WireGuard
# ---------------------------------------------------------------------------
step "Installing WireGuard"
apt-get update -qq
apt-get install -y wireguard wireguard-tools qrencode
success "WireGuard installed."

# ---------------------------------------------------------------------------
# 2. Generate server keypair
# ---------------------------------------------------------------------------
step "Generating server keypair"

mkdir -p /etc/wireguard
chmod 700 /etc/wireguard

SERVER_PRIV=$(wg genkey)
SERVER_PUB=$(echo "$SERVER_PRIV" | wg pubkey)

echo "$SERVER_PRIV" > /etc/wireguard/server.key
echo "$SERVER_PUB"  > /etc/wireguard/server.pub
chmod 600 /etc/wireguard/server.key
chmod 644 /etc/wireguard/server.pub

success "Server public key: $SERVER_PUB"

# ---------------------------------------------------------------------------
# 3. Detect primary network interface (used in PostUp/PostDown comments)
# ---------------------------------------------------------------------------
NET_IF=$(ip route show default | awk '/default via/{print $5; exit}')
[[ -n "$NET_IF" ]] || NET_IF="eth0"
info "Primary network interface: $NET_IF"

# ---------------------------------------------------------------------------
# 4. Write /etc/wireguard/wg0.conf
# ---------------------------------------------------------------------------
step "Writing server config: $WG_CONF"

cat > "$WG_CONF" <<EOF
# =============================================================================
# ArmGuard WireGuard Server — wg0
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# Managed by: setup-wireguard.sh / add-wireguard-peer.sh
# =============================================================================

[Interface]
PrivateKey = $SERVER_PRIV
Address    = ${WG_SERVER_IP}/24
ListenPort = $WG_PORT

# --- IP masquerade (needed only if clients use full-tunnel: AllowedIPs=0.0.0.0/0)
# For split-tunnel (default setup, AllowedIPs=10.8.0.0/24) these are optional.
# Enable if clients need to reach other LAN devices (192.168.0.x) via the VPN.
# PostUp   = iptables -t nat -A POSTROUTING -s ${WG_SUBNET} -o ${NET_IF} -j MASQUERADE
# PostDown = iptables -t nat -D POSTROUTING -s ${WG_SUBNET} -o ${NET_IF} -j MASQUERADE

# Peers are appended below by add-wireguard-peer.sh
EOF

chmod 600 "$WG_CONF"
success "Server config written to $WG_CONF"

# ---------------------------------------------------------------------------
# 5. Enable IP forwarding (needed for inter-client routing / full-tunnel)
# ---------------------------------------------------------------------------
step "Enabling IP forwarding"

if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.d/99-wireguard.conf 2>/dev/null; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.d/99-wireguard.conf
fi
sysctl -w net.ipv4.ip_forward=1 >/dev/null
success "IP forwarding enabled (persists via /etc/sysctl.d/99-wireguard.conf)."

# ---------------------------------------------------------------------------
# 6. Open firewall port
# ---------------------------------------------------------------------------
step "Opening UFW port ${WG_PORT}/udp for WireGuard"

if command -v ufw &>/dev/null; then
    ufw allow "${WG_PORT}/udp" comment "WireGuard VPN"
    success "UFW: allowed ${WG_PORT}/udp."
else
    warn "UFW not found — open port ${WG_PORT}/udp manually."
fi

# ---------------------------------------------------------------------------
# 7. Enable and start WireGuard
# ---------------------------------------------------------------------------
step "Enabling wg-quick@wg0 service"

systemctl enable wg-quick@wg0
systemctl start  wg-quick@wg0
success "WireGuard is running (wg-quick@wg0)."
wg show wg0

# ---------------------------------------------------------------------------
# 8. Regenerate SSL certificate to include WireGuard IP as SAN
# ---------------------------------------------------------------------------
if [[ "$REGEN_SSL" == "true" ]]; then
    step "Regenerating SSL certificate with WireGuard IP SAN (${WG_SERVER_IP})"

    # Detect existing SAN fields from the current cert so we don't lose them
    EXISTING_SANS=""
    if [[ -f "$CERT" ]]; then
        # Extract existing IPs (excluding the WG IP if already there)
        EXISTING_IPS=$(openssl x509 -noout -text -in "$CERT" 2>/dev/null \
            | grep -oP 'IP Address:\K[^\s,]+' \
            | grep -v "^${WG_SERVER_IP}$" \
            | sed 's/^/IP:/' | paste -sd',')
        EXISTING_DNS=$(openssl x509 -noout -text -in "$CERT" 2>/dev/null \
            | grep -oP 'DNS:\K[^\s,]+' \
            | sed 's/^/DNS:/' | paste -sd',')
        [[ -n "$EXISTING_IPS"  ]] && EXISTING_SANS="${EXISTING_IPS},"
        [[ -n "$EXISTING_DNS"  ]] && EXISTING_SANS="${EXISTING_SANS}${EXISTING_DNS},"
    fi

    # Default fallback if cert doesn't exist yet or parsing failed
    if [[ -z "$EXISTING_SANS" ]]; then
        EXISTING_SANS="IP:${SERVER_IP},DNS:${MDNS_HOST},"
    fi

    CERT_YEAR=$(date +%Y)
    openssl req -x509 -nodes -days 1095 -newkey rsa:2048 \
        -keyout "$KEY" \
        -out    "$CERT" \
        -subj   "/C=PH/ST=Metro Manila/L=Manila/O=ArmGuard RDS ${CERT_YEAR}/OU=Security/CN=${MDNS_HOST}" \
        -addext "subjectAltName=${EXISTING_SANS}IP:${WG_SERVER_IP}" \
        2>&1

    chmod 644 "$CERT"
    chmod 600 "$KEY"

    info "New SAN: ${EXISTING_SANS}IP:${WG_SERVER_IP}"
    success "SSL certificate regenerated (includes WireGuard IP ${WG_SERVER_IP})."

    # Reload nginx so the new cert is served immediately
    if systemctl is-active --quiet nginx; then
        systemctl reload nginx
        success "Nginx reloaded with new certificate."
    else
        warn "Nginx is not running — start it with: sudo systemctl start nginx"
    fi
fi

# ---------------------------------------------------------------------------
# 9. Update Django .env — add WireGuard IP to ALLOWED_HOSTS + CSRF_TRUSTED
# ---------------------------------------------------------------------------
step "Updating Django .env for WireGuard IP"

if [[ -f "$ENV_FILE" ]]; then
    # ── ALLOWED_HOSTS ──────────────────────────────────────────────────────
    CURRENT_HOSTS=$(grep "^DJANGO_ALLOWED_HOSTS=" "$ENV_FILE" | cut -d= -f2-)
    if [[ "$CURRENT_HOSTS" != *"$WG_SERVER_IP"* ]]; then
        sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${CURRENT_HOSTS},${WG_SERVER_IP}|" "$ENV_FILE"
        success "DJANGO_ALLOWED_HOSTS: added $WG_SERVER_IP"
    else
        info "DJANGO_ALLOWED_HOSTS already contains $WG_SERVER_IP — no change."
    fi

    # ── CSRF_TRUSTED_ORIGINS ───────────────────────────────────────────────
    CURRENT_CSRF=$(grep "^CSRF_TRUSTED_ORIGINS=" "$ENV_FILE" | cut -d= -f2-)
    WG_ORIGIN="https://${WG_SERVER_IP}"
    if [[ "$CURRENT_CSRF" != *"$WG_ORIGIN"* ]]; then
        sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=${CURRENT_CSRF},${WG_ORIGIN}|" "$ENV_FILE"
        success "CSRF_TRUSTED_ORIGINS: added $WG_ORIGIN"
    else
        info "CSRF_TRUSTED_ORIGINS already contains $WG_ORIGIN — no change."
    fi

    # Restart Gunicorn so Django picks up the new .env values
    if systemctl is-active --quiet armguard-gunicorn; then
        systemctl restart armguard-gunicorn
        success "armguard-gunicorn restarted."
    fi
else
    warn ".env not found at $ENV_FILE"
    warn "Add these lines manually after generating .env:"
    warn "  DJANGO_ALLOWED_HOSTS=...,${WG_SERVER_IP}"
    warn "  CSRF_TRUSTED_ORIGINS=...,https://${WG_SERVER_IP}"
fi

# ---------------------------------------------------------------------------
# 10. Generate first peer (client) config
# ---------------------------------------------------------------------------
if [[ "$MAKE_FIRST_PEER" == "true" ]]; then
    step "Generating first peer config"

    mkdir -p "$PEERS_DIR"
    chmod 700 "$PEERS_DIR"

    CLIENT_PRIV=$(wg genkey)
    CLIENT_PUB=$(echo "$CLIENT_PRIV" | wg pubkey)
    CLIENT_PSK=$(wg genpsk)   # Pre-shared key — extra layer of protection
    CLIENT_IP="10.8.0.2"
    PEER_CONF="$PEERS_DIR/peer1.conf"

    # Append peer to server config
    cat >> "$WG_CONF" <<EOF

[Peer]
# peer1 — generated $(date '+%Y-%m-%d')
PublicKey    = $CLIENT_PUB
PresharedKey = $CLIENT_PSK
AllowedIPs   = ${CLIENT_IP}/32
EOF

    # Hot-add peer to running WireGuard interface without restart
    wg set wg0 peer "$CLIENT_PUB" preshared-key <(echo "$CLIENT_PSK") allowed-ips "${CLIENT_IP}/32"

    # Write client .conf
    cat > "$PEER_CONF" <<EOF
# =============================================================================
# ArmGuard WireGuard — Client Config: peer1
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
#
# To use:
#   • Desktop/Linux : sudo wg-quick up /path/to/peer1.conf
#   • Android/iOS   : import via WireGuard app (scan the QR code below)
#   • Windows       : Import tunnel in the WireGuard app
#
# App access (after connecting):  https://${WG_SERVER_IP}
# You will be prompted to install the SSL certificate on first visit.
# =============================================================================

[Interface]
PrivateKey = $CLIENT_PRIV
Address    = ${CLIENT_IP}/32
DNS        = 1.1.1.1

[Peer]
PublicKey    = $SERVER_PUB
PresharedKey = $CLIENT_PSK
Endpoint     = ${SERVER_IP}:${WG_PORT}
AllowedIPs   = ${WG_SUBNET}
# AllowedIPs = 0.0.0.0/0, ::/0   # Uncomment for full-tunnel (route all traffic via VPN)
PersistentKeepalive = 25
EOF

    chmod 600 "$PEER_CONF"

    success "Peer 1 config written to: $PEER_CONF"
    echo
    echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD} peer1 — Client Config Summary${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
    echo -e "  VPN IP    : ${CYAN}${CLIENT_IP}${NC}"
    echo -e "  Endpoint  : ${CYAN}${SERVER_IP}:${WG_PORT}${NC}"
    echo -e "  App URL   : ${CYAN}https://${WG_SERVER_IP}${NC}"
    echo -e "  Conf file : ${CYAN}${PEER_CONF}${NC}"
    echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
    echo

    # Display QR code if qrencode is available (mobile import)
    if command -v qrencode &>/dev/null; then
        echo -e "${BOLD}Scan with the WireGuard mobile app:${NC}"
        qrencode -t ansiutf8 < "$PEER_CONF"
        echo
    fi

    warn "Keep $PEER_CONF private — it contains the client private key."
    warn "To add more clients: sudo bash scripts/add-wireguard-peer.sh"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN} WireGuard setup complete!${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "  Server VPN IP : ${CYAN}${WG_SERVER_IP}${NC}"
echo -e "  Listen port   : ${CYAN}${WG_PORT}/udp${NC}"
echo -e "  App URL (VPN) : ${CYAN}https://${WG_SERVER_IP}${NC}"
echo -e "  Server pub key: ${CYAN}${SERVER_PUB}${NC}"
echo
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "  1. Copy ${CYAN}${PEERS_DIR}/peer1.conf${NC} to the client device."
echo -e "  2. Import it in the WireGuard app and connect."
echo -e "  3. Browse to ${CYAN}https://${WG_SERVER_IP}${NC} and install the SSL cert."
echo -e "  4. Add more clients: ${CYAN}sudo bash scripts/add-wireguard-peer.sh${NC}"
echo
