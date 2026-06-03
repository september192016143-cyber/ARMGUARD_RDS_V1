#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# set-static-ip.sh — Configure a static LAN IP on Ubuntu (Netplan)
#
# Usage:
#   sudo bash scripts/set-static-ip.sh
#   sudo bash scripts/set-static-ip.sh --ip 10.100.5.52 --gateway 10.100.4.5 --prefix 22
#
# Options:
#   --ip       Static IP to assign (e.g. 10.100.5.52)
#   --gateway  Router/gateway IP (e.g. 10.100.4.5)
#   --prefix   Subnet prefix length in bits (default: 24; use 22 for /22 networks)
#   --dns      DNS servers, comma-separated (default: 8.8.8.8,8.8.4.4)
#   --iface    Network interface name (auto-detected if omitted)
#   --dry-run  Print the netplan YAML without applying
#   --auto     Non-interactive: use all auto-detected values; no prompts
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
# DEFAULT_IP and DEFAULT_GW are resolved at runtime after interface detection.
DEFAULT_DNS="8.8.8.8,8.8.4.4"
NETPLAN_FILE="/etc/netplan/99-armguard-static.yaml"
DRY_RUN=false

STATIC_IP=""
GATEWAY=""
DNS_SERVERS=""
IFACE=""
PREFIX=""           # subnet prefix bits; detected or prompted if empty

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip)      STATIC_IP="$2";   shift 2 ;;
    --gateway) GATEWAY="$2";     shift 2 ;;
    --prefix)  PREFIX="$2";      shift 2 ;;
    --dns)     DNS_SERVERS="$2"; shift 2 ;;
    --iface)   IFACE="$2";       shift 2 ;;
    --dry-run) DRY_RUN=true;     shift   ;;
    --auto)    AUTO=true;        shift   ;;   # non-interactive: use auto-detected values
    *) echo "Unknown option: $1"; exit 1  ;;
  esac
done

AUTO="${AUTO:-false}"

# ── Root check ────────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" == false ]] && [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run with sudo: sudo bash $0"
  exit 1
fi

# ── Auto-detect interface ─────────────────────────────────────────────────────
if [[ -z "$IFACE" ]]; then
  IFACE=$(ip -o -4 route show to default 2>/dev/null | awk '{print $5}' | head -n1)
  if [[ -z "$IFACE" ]]; then
    echo "ERROR: Could not auto-detect network interface. Pass --iface <name>."
    exit 1
  fi
  echo "Auto-detected interface: $IFACE"
fi

# ── Detect current IP and gateway as smart defaults ───────────────────────────
DEFAULT_IP=$(ip -4 addr show "$IFACE" 2>/dev/null \
  | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1)
DEFAULT_IP="${DEFAULT_IP:-10.100.5.52}"

DEFAULT_GW=$(ip -4 route show default 2>/dev/null | awk '{print $3}' | head -n1)
DEFAULT_GW="${DEFAULT_GW:-10.100.4.5}"

# Detect current prefix length for smart default (e.g. /22 for 10.100.x.x)
DEFAULT_PREFIX=$(ip -4 addr show "$IFACE" 2>/dev/null \
  | grep -oP '(?<=inet\s)\d+(\.\d+){3}/\K\d+' | head -n1)
DEFAULT_PREFIX="${DEFAULT_PREFIX:-24}"

# ── Interactive prompts for missing values (skipped with --auto) ──────────────
if [[ "$AUTO" == true ]]; then
  STATIC_IP="${STATIC_IP:-$DEFAULT_IP}"
  GATEWAY="${GATEWAY:-$DEFAULT_GW}"
  PREFIX="${PREFIX:-$DEFAULT_PREFIX}"
  DNS_SERVERS="${DNS_SERVERS:-$DEFAULT_DNS}"
  echo "Auto mode: IP=${STATIC_IP}/${PREFIX}  GW=${GATEWAY}  DNS=${DNS_SERVERS}  iface=${IFACE}"
else
  if [[ -z "$STATIC_IP" ]]; then
    read -rp "Static IP address [${DEFAULT_IP}]: " STATIC_IP
    STATIC_IP="${STATIC_IP:-$DEFAULT_IP}"
  fi

  if [[ -z "$GATEWAY" ]]; then
    read -rp "Gateway (router) IP [${DEFAULT_GW}]: " GATEWAY
    GATEWAY="${GATEWAY:-$DEFAULT_GW}"
  fi

  if [[ -z "$PREFIX" ]]; then
    read -rp "Subnet prefix bits (e.g. 22 for /22, 24 for /24) [${DEFAULT_PREFIX}]: " PREFIX
    PREFIX="${PREFIX:-$DEFAULT_PREFIX}"
  fi

  if [[ -z "$DNS_SERVERS" ]]; then
    read -rp "DNS servers, comma-separated [${DEFAULT_DNS}]: " DNS_SERVERS
    DNS_SERVERS="${DNS_SERVERS:-$DEFAULT_DNS}"
  fi
fi

# ── Format DNS for YAML list ──────────────────────────────────────────────────
DNS_YAML=$(echo "$DNS_SERVERS" | tr ',' '\n' | sed 's/^[[:space:]]*//' | awk '{print "          - "$1}')

# ── Show current config ───────────────────────────────────────────────────────
echo ""
echo "Current IP configuration:"
ip -4 addr show "$IFACE" 2>/dev/null || true
echo ""

# ── Build netplan YAML ────────────────────────────────────────────────────────
YAML_CONTENT="network:
  version: 2
  renderer: networkd
  ethernets:
    ${IFACE}:
      dhcp4: no
      addresses:
        - ${STATIC_IP}/${PREFIX}
      routes:
        - to: default
          via: ${GATEWAY}
      nameservers:
        addresses:
${DNS_YAML}
"

echo "──────────────────────────────────────────────"
echo "Netplan config to be written → ${NETPLAN_FILE}"
echo "──────────────────────────────────────────────"
echo "$YAML_CONTENT"

if [[ "$DRY_RUN" == true ]]; then
  echo "[dry-run] No changes made."
  exit 0
fi

# ── Backup existing netplan files ─────────────────────────────────────────────
BACKUP_DIR="/etc/netplan/backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp /etc/netplan/*.yaml "$BACKUP_DIR/" 2>/dev/null || true
echo "Existing netplan files backed up to: $BACKUP_DIR"

# ── Disable DHCP in any existing config for this interface ───────────────────
for f in /etc/netplan/*.yaml; do
  [[ "$f" == "$NETPLAN_FILE" ]] && continue
  if grep -q "$IFACE" "$f" 2>/dev/null; then
    echo "Note: $f also references $IFACE — you may want to review it."
  fi
done

# ── Write and apply ───────────────────────────────────────────────────────────
echo "$YAML_CONTENT" > "$NETPLAN_FILE"
chmod 600 "$NETPLAN_FILE"
echo "Written: $NETPLAN_FILE"

echo ""
echo "Applying netplan configuration…"
netplan apply

echo ""
echo "──────────────────────────────────────────────"
echo "New IP configuration:"
ip -4 addr show "$IFACE"
echo "──────────────────────────────────────────────"
echo "Done. Server is now configured with static IP: ${STATIC_IP}"
echo "Verify connectivity: ping ${GATEWAY}"
