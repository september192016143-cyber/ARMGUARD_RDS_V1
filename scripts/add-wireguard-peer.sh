#!/usr/bin/env bash
# =============================================================================
# ARMGUARD RDS V1 — WireGuard: Add Peer (Client)
# =============================================================================
# Generates a new WireGuard peer config and adds it to the running server.
# Must be run AFTER setup-wireguard.sh has been used to initialise wg0.
#
# Usage:
#   sudo bash scripts/add-wireguard-peer.sh [OPTIONS]
#
# Options:
#   --name NAME    Human label for this peer.  Used as a comment in the
#                  config and as the filename (default: peer<N>)
#   --ip IP        Assign a specific 10.8.0.x address (default: next free)
#   --help         Show this help
#
# The generated client config is written to /etc/wireguard/peers/<name>.conf
# and its QR code is printed to the terminal for mobile import.
# =============================================================================

set -Eeo pipefail

WG_CONF="/etc/wireguard/wg0.conf"
PEERS_DIR="/etc/wireguard/peers"

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
step()    { echo -e "\n${BOLD}>>> $*${NC}"; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
PEER_NAME=""
CLIENT_IP_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name) PEER_NAME="$2"; shift 2 ;;
        --ip)   CLIENT_IP_OVERRIDE="$2"; shift 2 ;;
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

[[ -f "$WG_CONF" ]] || die "WireGuard not configured.  Run setup-wireguard.sh first."

command -v wg       &>/dev/null || die "'wg' not found.  Install WireGuard: apt-get install wireguard-tools"
command -v wg-quick &>/dev/null || die "'wg-quick' not found."

# Verify wg0 is up
wg show wg0 &>/dev/null || die "wg0 interface is not running.  Start it: sudo systemctl start wg-quick@wg0"

mkdir -p "$PEERS_DIR"
chmod 700 "$PEERS_DIR"

# ---------------------------------------------------------------------------
# Determine next available peer number and IP
# ---------------------------------------------------------------------------
step "Determining next available peer slot"

# Find the highest 10.8.0.x IP already assigned in wg0.conf
LAST_OCTET=$(grep -oP '10\.8\.0\.\K[0-9]+(?=/32)' "$WG_CONF" | sort -n | tail -1)
NEXT_OCTET=$(( ${LAST_OCTET:-1} + 1 ))

if [[ "$NEXT_OCTET" -ge 255 ]]; then
    die "WireGuard subnet is full (10.8.0.0/24 supports up to 253 peers)."
fi

# Resolve IP
if [[ -n "$CLIENT_IP_OVERRIDE" ]]; then
    CLIENT_IP="$CLIENT_IP_OVERRIDE"
    # Validate the override is in 10.8.0.x range and not already in use
    if grep -q "AllowedIPs\s*=\s*${CLIENT_IP}/32" "$WG_CONF"; then
        die "IP ${CLIENT_IP} is already assigned in $WG_CONF"
    fi
else
    CLIENT_IP="10.8.0.${NEXT_OCTET}"
fi

# Determine peer name / filename
PEER_NUMBER=$(( $(grep -c '^\[Peer\]' "$WG_CONF" || true) + 0 ))
# +1 to get the new peer number (grep -c returns matched count: existing peers)
PEER_NUMBER=$(( PEER_NUMBER + 1 ))
[[ -z "$PEER_NAME" ]] && PEER_NAME="peer${PEER_NUMBER}"

PEER_CONF="${PEERS_DIR}/${PEER_NAME}.conf"
[[ -f "$PEER_CONF" ]] && die "Peer config already exists: $PEER_CONF  Choose a different --name."

info "New peer: ${PEER_NAME}  IP: ${CLIENT_IP}"

# ---------------------------------------------------------------------------
# Read server info from wg0.conf + running interface
# ---------------------------------------------------------------------------
SERVER_PUB=$(wg show wg0 public-key)
SERVER_ENDPOINT=$(grep -oP '(?<=Endpoint = ).*' "${PEERS_DIR}/peer1.conf" 2>/dev/null \
    || echo "")

# Fall back: derive from server public IP if peer1.conf isn't readable
if [[ -z "$SERVER_ENDPOINT" ]]; then
    # Prefer public hostname from wg0.conf comment section
    warn "Could not auto-detect server endpoint from peer1.conf."
    warn "Set the Endpoint manually in: $PEER_CONF"
    SERVER_ENDPOINT="<SERVER_IP>:$(wg show wg0 listen-port)"
fi

WG_PORT=$(wg show wg0 listen-port)

# ---------------------------------------------------------------------------
# Generate peer keypair + preshared key
# ---------------------------------------------------------------------------
step "Generating keypair for ${PEER_NAME}"

CLIENT_PRIV=$(wg genkey)
CLIENT_PUB=$(echo "$CLIENT_PRIV" | wg pubkey)
CLIENT_PSK=$(wg genpsk)

success "Public key: $CLIENT_PUB"

# ---------------------------------------------------------------------------
# Append peer to server config file
# ---------------------------------------------------------------------------
step "Adding ${PEER_NAME} to server config"

cat >> "$WG_CONF" <<EOF

[Peer]
# ${PEER_NAME} — added $(date '+%Y-%m-%d')
PublicKey    = $CLIENT_PUB
PresharedKey = $CLIENT_PSK
AllowedIPs   = ${CLIENT_IP}/32
EOF

# Hot-add peer to running WireGuard interface (no restart needed)
wg set wg0 peer "$CLIENT_PUB" preshared-key <(echo "$CLIENT_PSK") allowed-ips "${CLIENT_IP}/32"
success "${PEER_NAME} added to wg0 (hot-reload — no restart needed)."

# ---------------------------------------------------------------------------
# Write client .conf file
# ---------------------------------------------------------------------------
step "Writing client config: $PEER_CONF"

cat > "$PEER_CONF" <<EOF
# =============================================================================
# ArmGuard WireGuard — Client Config: ${PEER_NAME}
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
#
# To use:
#   • Desktop/Linux : sudo wg-quick up /path/to/${PEER_NAME}.conf
#   • Android/iOS   : import via WireGuard app (scan QR code below)
#   • Windows       : Import tunnel in the WireGuard desktop app
#
# App access (after connecting): https://10.8.0.1
# Install the SSL cert at /download/ssl-cert/ on first visit.
# =============================================================================

[Interface]
PrivateKey = $CLIENT_PRIV
Address    = ${CLIENT_IP}/32
DNS        = 1.1.1.1

[Peer]
PublicKey    = $SERVER_PUB
PresharedKey = $CLIENT_PSK
Endpoint     = $SERVER_ENDPOINT
AllowedIPs   = 10.8.0.0/24
# AllowedIPs = 0.0.0.0/0, ::/0   # Uncomment to route all traffic through VPN
PersistentKeepalive = 25
EOF

chmod 600 "$PEER_CONF"
success "Client config written to: $PEER_CONF"

# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} ${PEER_NAME} — Client Config Summary${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo -e "  VPN IP    : ${CYAN}${CLIENT_IP}${NC}"
echo -e "  Endpoint  : ${CYAN}${SERVER_ENDPOINT}${NC}"
echo -e "  App URL   : ${CYAN}https://10.8.0.1${NC}"
echo -e "  Conf file : ${CYAN}${PEER_CONF}${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════${NC}"
echo

# QR code for mobile import
if command -v qrencode &>/dev/null; then
    echo -e "${BOLD}Scan with the WireGuard mobile app:${NC}"
    qrencode -t ansiutf8 < "$PEER_CONF"
    echo
else
    info "Install qrencode for a QR code: apt-get install qrencode"
fi

warn "Keep $PEER_CONF private — it contains the client private key."

# Show current peer list
echo -e "\n${BOLD}Current peers on wg0:${NC}"
wg show wg0 peers | while read -r pub; do
    echo "  $pub"
done
echo
