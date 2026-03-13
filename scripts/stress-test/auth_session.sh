#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Stress Test Session Cookie Helper
# =============================================================================
# Run this FIRST from the LOAD GENERATOR machine (Dev PC: 192.168.0.82).
# It logs in, handles TOTP MFA, and writes cookies to /tmp/armguard_session.env.
#
# Usage:
#   source <(./scripts/stress-test/auth_session.sh http://192.168.0.11 admin password)
#
# With TOTP (MFA is required for all users):
#   TOTP_SECRET=BASE32SECRET \
#     source <(./scripts/stress-test/auth_session.sh http://192.168.0.11 admin password)
#
# Outputs (exported into caller's shell via source <(...)  ):
#   SESSION_COOKIE="sessionid=<value>"
#   CSRF_TOKEN="<value>"
#   AUTH_COOKIE_HEADER="sessionid=<value>; csrftoken=<value>"
#   STRESS_BASE_URL="http://192.168.0.11"
#
# Status messages go to stderr so they don't interfere with source <(...).
# Requires: curl, python3 + pyotp (for TOTP step — pip install pyotp)
# =============================================================================

set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────
BASE_URL="${1:-http://192.168.0.11}"
USERNAME="${2:-${STRESS_TEST_USER:-}}"
PASSWORD="${3:-${STRESS_TEST_PASSWORD:-}}"

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
    echo "[auth_session] ERROR: USERNAME and PASSWORD are required." >&2
    echo "[auth_session] Usage: source <(./auth_session.sh BASE_URL USERNAME PASSWORD)" >&2
    echo "[auth_session] Or set STRESS_TEST_USER and STRESS_TEST_PASSWORD env vars." >&2
    exit 1
fi

LOGIN_URL="${BASE_URL}/accounts/login/"
OTP_VERIFY_URL="${BASE_URL}/accounts/otp/verify/"
DASHBOARD_URL="${BASE_URL}/dashboard/"

# Temporary cookie jar — automatically removed on exit
COOKIE_JAR=$(mktemp /tmp/armguard_cookies_XXXXXX)
trap 'rm -f "$COOKIE_JAR"' EXIT

STATUS() { echo "[auth_session] $*" >&2; }

# ── Step 1: GET /accounts/login/ to receive the initial CSRF cookie ───────────
STATUS "Fetching login page: $LOGIN_URL"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -c "$COOKIE_JAR" \
    "$LOGIN_URL")

if [[ "$HTTP_CODE" != "200" ]]; then
    echo "[auth_session] ERROR: Login page returned HTTP $HTTP_CODE (expected 200)." >&2
    echo "[auth_session]        Is the server running? Check: ssh armguard@192.168.0.11 sudo systemctl status armguard-gunicorn" >&2
    exit 1
fi

# Extract csrftoken value from the cookie jar file
CSRF_TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -1)
if [[ -z "$CSRF_TOKEN" ]]; then
    echo "[auth_session] ERROR: Could not extract CSRF token from login page." >&2
    exit 1
fi
STATUS "CSRF token obtained: ${CSRF_TOKEN:0:8}..."

# ── Step 2: POST credentials ──────────────────────────────────────────────────
STATUS "Posting credentials for user: $USERNAME"

# Follow redirects and capture the final URL to detect MFA redirect
FINAL_URL=$(curl -s -o /tmp/armguard_login_resp.html \
    -w "%{url_effective}" \
    -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -X POST "$LOGIN_URL" \
    --data-urlencode "username=${USERNAME}" \
    --data-urlencode "password=${PASSWORD}" \
    -d "csrfmiddlewaretoken=${CSRF_TOKEN}" \
    -H "Referer: ${LOGIN_URL}" \
    --max-redirs 5 \
    -L) || true

SESSION_ID=$(awk '$6 == "sessionid" {print $7}' "$COOKIE_JAR" | tail -1)

if [[ -z "$SESSION_ID" ]]; then
    echo "[auth_session] ERROR: Authentication failed — no sessionid cookie." >&2
    echo "[auth_session]        Check that USERNAME ($USERNAME) and PASSWORD are correct." >&2
    exit 1
fi
STATUS "Session cookie obtained: ${SESSION_ID:0:8}..."

# ── Step 3: Handle TOTP MFA if redirected to /accounts/otp/verify/ ───────────
if echo "$FINAL_URL" | grep -q "otp/verify"; then
    STATUS "MFA redirect detected — proceeding with TOTP verification."

    TOTP_SECRET="${TOTP_SECRET:-}"
    if [[ -z "$TOTP_SECRET" ]]; then
        echo "[auth_session] ERROR: Server requires TOTP but TOTP_SECRET is not set." >&2
        echo "[auth_session]        Export the base32 secret string from the user's authenticator app:" >&2
        echo "[auth_session]          export TOTP_SECRET=JBSWY3DPEHPK3PXP" >&2
        exit 1
    fi

    # Generate current 6-digit TOTP code using pyotp
    TOTP_CODE=$(python3 -c "
import pyotp, sys
try:
    print(pyotp.TOTP('${TOTP_SECRET}').now())
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null) || {
        echo "[auth_session] ERROR: Failed to generate TOTP code." >&2
        echo "[auth_session]        Ensure pyotp is installed: pip3 install pyotp" >&2
        exit 1
    }
    STATUS "Generated TOTP code: $TOTP_CODE"

    # Refresh CSRF token for the OTP verify form
    CSRF_TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -1)

    FINAL_URL=$(curl -s -o /tmp/armguard_otp_resp.html \
        -w "%{url_effective}" \
        -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
        -X POST "$OTP_VERIFY_URL" \
        -d "token=${TOTP_CODE}&csrfmiddlewaretoken=${CSRF_TOKEN}&next=dashboard" \
        -H "Referer: ${OTP_VERIFY_URL}" \
        --max-redirs 5 \
        -L) || true

    # After OTP, session may be refreshed
    SESSION_ID=$(awk '$6 == "sessionid" {print $7}' "$COOKIE_JAR" | tail -1)
    CSRF_TOKEN=$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -1)

    STATUS "OTP submitted. Final URL: $FINAL_URL"
fi

# ── Step 4: Verify the session reaches /dashboard/ (HTTP 200, not 302) ───────
STATUS "Verifying session: GET $DASHBOARD_URL"
VERIFY_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -b "sessionid=${SESSION_ID}; csrftoken=${CSRF_TOKEN}" \
    "$DASHBOARD_URL")

if [[ "$VERIFY_CODE" != "200" ]]; then
    echo "[auth_session] ERROR: Session check failed — GET /dashboard/ returned HTTP $VERIFY_CODE." >&2
    echo "[auth_session]        Login or MFA step may not have completed. Got response: $FINAL_URL" >&2
    exit 1
fi
STATUS "Session verified — /dashboard/ returned HTTP 200."

# ── Step 5: Write session env file (also used by stress_test.sh) ─────────────
cat > /tmp/armguard_session.env <<EOF
export SESSION_COOKIE="sessionid=${SESSION_ID}"
export CSRF_TOKEN="${CSRF_TOKEN}"
export AUTH_COOKIE_HEADER="sessionid=${SESSION_ID}; csrftoken=${CSRF_TOKEN}"
export STRESS_BASE_URL="${BASE_URL}"
EOF

STATUS "Written to /tmp/armguard_session.env"
STATUS "Run: source /tmp/armguard_session.env"

# ── Output export lines (captured by source <(...) ) ─────────────────────────
printf 'export SESSION_COOKIE="sessionid=%s"\n' "$SESSION_ID"
printf 'export CSRF_TOKEN="%s"\n' "$CSRF_TOKEN"
printf 'export AUTH_COOKIE_HEADER="sessionid=%s; csrftoken=%s"\n' "$SESSION_ID" "$CSRF_TOKEN"
printf 'export STRESS_BASE_URL="%s"\n' "$BASE_URL"
