#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# armguard-autoip.sh — Auto-detect live IP and promote to static if changed
#
# Designed to run as a systemd one-shot service (armguard-autoip.service) on
# every boot BEFORE armguard-gunicorn starts.
#
# Behaviour:
#   1. Reads the current IP assigned to the default-route interface (DHCP or static).
#   2. Compares it with what is already written in the Netplan static config.
#   3. If they match  → does nothing (already correct).
#   4. If they differ → calls set-static-ip.sh --auto to promote the live IP
#      to static so it never changes again on this network.
#
# Use-case — moving the server to a different network:
#   Transfer server → first boot gets a new DHCP IP → this service fires →
#   detects the new IP → sets it static → subsequent boots keep the same IP.
#   Clients find the server via "armguard.local" (mDNS / Avahi) regardless of
#   which IP the server ends up with.
#
# Run manually:
#   sudo bash /var/www/ARMGUARD_RDS_V1/scripts/armguard-autoip.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

NETPLAN_FILE="/etc/netplan/99-armguard-static.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="[armguard-autoip]"

# ── Detect live network state ─────────────────────────────────────────────────
IFACE=$(ip -o -4 route show to default 2>/dev/null | awk '{print $5}' | head -n1)

if [[ -z "$IFACE" ]]; then
    echo "$LOG No default route found — network not ready yet. Skipping."
    exit 0
fi

LIVE_IP=$(ip -4 addr show "$IFACE" 2>/dev/null \
    | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1)

if [[ -z "$LIVE_IP" ]]; then
    echo "$LOG No IP assigned to $IFACE. Skipping."
    exit 0
fi

LIVE_PREFIX=$(ip -4 addr show "$IFACE" 2>/dev/null \
    | grep -oP '(?<=inet\s)\d+(\.\d+){3}/\K\d+' | head -n1)
LIVE_PREFIX="${LIVE_PREFIX:-24}"

LIVE_GW=$(ip -4 route show default 2>/dev/null | awk '{print $3}' | head -n1)

echo "$LOG Detected: ${LIVE_IP}/${LIVE_PREFIX}  GW=${LIVE_GW}  iface=${IFACE}"

# ── Skip if static config already matches ────────────────────────────────────
if [[ -f "$NETPLAN_FILE" ]] \
   && grep -q "${LIVE_IP}/${LIVE_PREFIX}" "$NETPLAN_FILE" 2>/dev/null \
   && grep -q "via: ${LIVE_GW}" "$NETPLAN_FILE" 2>/dev/null; then
    echo "$LOG Static config already matches live IP. Nothing to do."
    exit 0
fi

# ── Promote live IP to static ─────────────────────────────────────────────────
if [[ -f "$NETPLAN_FILE" ]]; then
    echo "$LOG Existing static config does not match live IP — updating."
else
    echo "$LOG No static config found — creating one from live IP."
fi

bash "$SCRIPT_DIR/set-static-ip.sh" \
    --auto \
    --ip     "$LIVE_IP" \
    --gateway "$LIVE_GW" \
    --prefix  "$LIVE_PREFIX" \
    --iface   "$IFACE"

echo "$LOG Done. Server is now static at ${LIVE_IP}/${LIVE_PREFIX}."
echo "$LOG Clients can reach the server via: http://armguard.local  OR  http://${LIVE_IP}"
