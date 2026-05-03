#!/usr/bin/env bash
# =============================================================================
# renew-ssl-cert.sh — Auto-renew ArmGuard self-signed SSL certificate
# =============================================================================
#
# Run monthly via cron (installed automatically by deploy.sh).
# Regenerates the certificate if it expires within RENEW_BEFORE_DAYS days.
#
# After renewal the ArmGuard web app detects the new certificate and shows a
# notification to each logged-in user prompting them to download and reinstall
# it on their device (click "Install SSL Cert" in the sidebar footer).
#
# Usage:   sudo bash scripts/renew-ssl-cert.sh
# Cron:    0 3 1 * * /var/www/ARMGUARD_RDS_V1/scripts/renew-ssl-cert.sh >> /var/log/armguard/ssl-renewal.log 2>&1
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — edit SERVER_IP if the LAN IP changes
# ---------------------------------------------------------------------------
CERT="/etc/ssl/certs/armguard-selfsigned.crt"
KEY="/etc/ssl/private/armguard-selfsigned.key"
SERVER_IP="192.168.0.11"
RENEW_BEFORE_DAYS=45          # Renew this many days before expiry
CERT_VALIDITY_DAYS=1095       # 3 years for new cert

LOG_DIR="/var/log/armguard"
LOG="$LOG_DIR/ssl-renewal.log"

mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo)." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Verify cert exists
# ---------------------------------------------------------------------------
if [[ ! -f "$CERT" ]]; then
    log "ERROR: Certificate not found at $CERT"
    log "       Run the initial SSL setup first (see scripts/SSL_SELFSIGNED.md)."
    exit 1
fi

# ---------------------------------------------------------------------------
# Check days remaining until expiry
# ---------------------------------------------------------------------------
EXPIRY_RAW=$(openssl x509 -enddate -noout -in "$CERT" | cut -d= -f2)

# Try GNU date (Linux), fall back to BSD date (macOS)
EXPIRY_EPOCH=$(date -d "$EXPIRY_RAW" +%s 2>/dev/null \
    || date -j -f "%b %d %H:%M:%S %Y %Z" "$EXPIRY_RAW" +%s 2>/dev/null \
    || { log "ERROR: Could not parse cert expiry date: $EXPIRY_RAW"; exit 1; })

NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

log "Certificate: CN=$SERVER_IP | Expires in $DAYS_LEFT day(s) ($EXPIRY_RAW)"

# ---------------------------------------------------------------------------
# Decide whether to renew
# ---------------------------------------------------------------------------
if [[ "$DAYS_LEFT" -gt "$RENEW_BEFORE_DAYS" ]]; then
    log "Renewal not needed (threshold: $RENEW_BEFORE_DAYS days). No action taken."
    exit 0
fi

log "Renewing — expires in $DAYS_LEFT day(s), within the ${RENEW_BEFORE_DAYS}-day renewal window..."

# ---------------------------------------------------------------------------
# Generate new certificate
# ---------------------------------------------------------------------------
RENEW_YEAR=$(date +%Y)
openssl req -x509 -nodes -days "$CERT_VALIDITY_DAYS" -newkey rsa:2048 \
    -keyout "$KEY" \
    -out    "$CERT" \
    -subj   "/C=PH/ST=Metro Manila/L=Manila/O=ArmGuard RDS ${RENEW_YEAR}/OU=Security/CN=ArmGuard RDS ${RENEW_YEAR}" \
    -addext "subjectAltName=IP:$SERVER_IP" \
    2>&1 | tee -a "$LOG"

chmod 644 "$CERT"
chmod 600 "$KEY"

# ---------------------------------------------------------------------------
# Reload nginx so the new cert is served immediately
# ---------------------------------------------------------------------------
if systemctl reload nginx 2>&1 | tee -a "$LOG"; then
    log "nginx reloaded successfully."
else
    log "WARNING: nginx reload failed — check 'sudo nginx -t' for syntax errors."
fi

log "Certificate renewed. Valid for ${CERT_VALIDITY_DAYS} days from today."
log "Users will be notified in the ArmGuard interface to reinstall the certificate."
log "They can click 'Install SSL Cert' in the sidebar, or visit /download/ssl-cert/."
