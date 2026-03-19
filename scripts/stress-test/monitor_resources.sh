#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Background Resource Monitor
# =============================================================================
# Run this ON THE SERVER (the machine running ArmGuard RDS), not on the load generator.
# stress_test.sh starts this automatically via SSH when SERVER_SSH is set.
# You can also start it manually before running the stress test.
#
# Usage (manual, run on server):
#   bash scripts/stress-test/monitor_resources.sh [OUTPUT_CSV]
#
# Default output file: /tmp/armguard_resources.csv
# Samples every 5 seconds until killed (SIGTERM/SIGINT).
#
# CSV columns:
#   timestamp, cpu_percent, ram_used_mb, swap_used_mb, load_avg_1m,
#   gunicorn_workers_active, db_connections
#
# Note: db_connections column is always 0 for SQLite (no port to count).
#       Column is kept for report compatibility with PostgreSQL setups.
# =============================================================================

set -euo pipefail

OUTPUT_CSV="${1:-/tmp/armguard_resources.csv}"
INTERVAL=5   # seconds between samples

# Write CSV header only if file does not already exist (idempotent restart)
if [[ ! -f "$OUTPUT_CSV" ]]; then
    echo "timestamp,cpu_percent,ram_used_mb,swap_used_mb,load_avg_1m,gunicorn_workers_active,db_connections" \
        > "$OUTPUT_CSV"
fi

echo "[monitor] Started. Writing to $OUTPUT_CSV every ${INTERVAL}s. PID=$$" >&2
echo "[monitor] DB engine: sqlite3 — db_connections column will always be 0." >&2

# ── Cleanup on signal ─────────────────────────────────────────────────────────
trap 'echo "[monitor] Stopped (PID=$$)." >&2; exit 0' SIGTERM SIGINT

while true; do
    # ── Timestamp ─────────────────────────────────────────────────────────────
    TS=$(date '+%Y-%m-%d %H:%M:%S')

    # ── CPU % (idle reported by top; subtract from 100) ───────────────────────
    # top -bn1 prints one batch-mode snapshot; the "Cpu(s)" line looks like:
    #   %Cpu(s):  4.3 us,  1.2 sy,  0.0 ni, 93.8 id, ...
    # We extract "id" (idle) and compute used = 100 - idle.
    CPU_IDLE=$(top -bn1 2>/dev/null \
        | grep -E "^(%Cpu|Cpu)" \
        | awk '{for(i=1;i<=NF;i++) if($i ~ /id,?/) {gsub(/[^0-9.]/,"",$i); print $i; exit}}')
    CPU_PCT=$(awk "BEGIN{printf \"%.1f\", 100 - ${CPU_IDLE:-0}}")

    # ── RAM & Swap (free -m gives values in MiB) ────────────────────────────
    RAM_USED=$(free -m 2>/dev/null \
        | awk '/^Mem:/ {print $3}')
    SWAP_USED=$(free -m 2>/dev/null \
        | awk '/^Swap:/ {print $3}')

    # ── 1-minute load average (first field of /proc/loadavg) ─────────────────
    LOAD_1M=$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo "0")

    # ── Active Gunicorn worker processes ──────────────────────────────────────
    # Count all gunicorn processes (master + workers); subtract 1 for master.
    GUNICORN_TOTAL=$(ps aux 2>/dev/null \
        | grep -c '[g]unicorn' || echo 0)
    GUNICORN_WORKERS=$(( GUNICORN_TOTAL > 1 ? GUNICORN_TOTAL - 1 : GUNICORN_TOTAL ))

    # ── DB connections: SQLite → always 0 ─────────────────────────────────────
    # For a PostgreSQL setup this would be:
    #   ss -tn | grep -c ':5432' || echo 0
    DB_CONNECTIONS=0

    # ── Append CSV row ─────────────────────────────────────────────────────────
    echo "${TS},${CPU_PCT},${RAM_USED:-0},${SWAP_USED:-0},${LOAD_1M},${GUNICORN_WORKERS},${DB_CONNECTIONS}" \
        >> "$OUTPUT_CSV"

    sleep "$INTERVAL"
done
