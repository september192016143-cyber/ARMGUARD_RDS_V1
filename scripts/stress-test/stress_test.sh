#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Stress Test Master Orchestrator
# =============================================================================
# Run this from the LOAD GENERATOR machine (Dev PC: 192.168.0.82).
# DO NOT run this on the server — results will be misleading.
#
# Prerequisites:
#   1. source <(./scripts/stress-test/auth_session.sh http://192.168.0.11 USER PASS)
#   2. (Optional) export SERVER_SSH="armguard@192.168.0.11" for remote monitoring
#
# Usage:
#   ./scripts/stress-test/stress_test.sh [--dry-run] [--force-local]
#
# Environment variables (all optional overrides):
#   SERVER_IP        Target server IP      (default: 192.168.0.11)
#   SERVER_PROTOCOL  http or https         (default: http)
#   SERVER_SSH       SSH target for remote resource monitoring
#                    Example: armguard@192.168.0.11
#   RESULTS_DIR      Override output dir   (default: ~/armguard-stress-results)
# =============================================================================

set -euo pipefail

# ── Known values (from deployed codebase) ────────────────────────────────────
SERVER_IP="${SERVER_IP:-192.168.0.11}"
SERVER_PROTOCOL="${SERVER_PROTOCOL:-http}"
BASE_URL="${SERVER_PROTOCOL}://${SERVER_IP}"
DB_ENGINE="sqlite3"
CONN_MAX_AGE=600
DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"

# ── Runtime detection ─────────────────────────────────────────────────────────
LOAD_GENERATOR_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M')
RESULTS_BASE="${RESULTS_DIR:-${HOME}/armguard-stress-results}"
OUTPUT_DIR="$RESULTS_BASE/$TIMESTAMP"

# ── Concurrency levels (500 added when RAM >= 8 GB — checked at runtime) ─────
BASE_LEVELS=(1 10 25 50 100 200)

# ── Flags ─────────────────────────────────────────────────────────────────────
DRY_RUN=false
FORCE_LOCAL=false
HAVE_AB=false
HAVE_WRK=false
HAVE_LOCUST=false
STOP_ESCALATION=false
MONITOR_PID=""

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[STRESS]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}    $*"; }
err()  { echo -e "${RED}[ERROR]${NC}   $*" >&2; exit 1; }
ok()   { echo -e "${GREEN}[PASS]${NC}    $*"; }
fail() { echo -e "${RED}[FAIL]${NC}    $*"; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)     DRY_RUN=true;     shift ;;
        --force-local) FORCE_LOCAL=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--force-local]"
            echo "  --dry-run      Print all commands without sending any load."
            echo "  --force-local  Bypass same-host safety guard (results misleading)."
            exit 0 ;;
        *) err "Unknown argument: $1" ;;
    esac
done

# ── OS check: Ubuntu 20.04+ required on the SERVER (we just check locally) ───
# (Server OS validated by deploy.sh; this guard only blocks obviously wrong OS)
if [[ "$(uname -s)" != "Linux" ]] && [[ "$(uname -s)" != "Darwin" ]]; then
    err "Load generator must be Linux or macOS. Found: $(uname -s)"
fi

# ── Same-host safety guard ────────────────────────────────────────────────────
# Running ab/wrk/locust on the server host inflates latency and deflates RPS.
if [[ "$LOAD_GENERATOR_IP" == "$SERVER_IP" ]] && [[ "$FORCE_LOCAL" == "false" ]]; then
    err "SAFETY: Load generator IP ($LOAD_GENERATOR_IP) == Server IP ($SERVER_IP).
Run this script from a separate machine (e.g. Dev PC 192.168.0.82).
Pass --force-local to override (results will NOT be reliable)."
fi

[[ "$DRY_RUN" == "true" ]] && warn "DRY-RUN mode — no load will be sent."

# ── Helper: run a command or print it in dry-run mode ────────────────────────
run_cmd() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  [DRY-RUN] $*"
    else
        "$@"
    fi
}

# ── Install missing tools (Ubuntu/Debian load generator only) ─────────────────
detect_and_install_tools() {
    command -v ab      &>/dev/null && HAVE_AB=true
    command -v wrk     &>/dev/null && HAVE_WRK=true
    command -v locust  &>/dev/null && HAVE_LOCUST=true

    if [[ "$DRY_RUN" == "true" ]]; then
        log "Tools detected: ab=$HAVE_AB  wrk=$HAVE_WRK  locust=$HAVE_LOCUST"
        return
    fi

    if command -v apt-get &>/dev/null; then
        if [[ "$HAVE_AB" == "false" ]]; then
            log "Installing apache2-utils (ab)..."
            sudo apt-get install -y -q apache2-utils; HAVE_AB=true
        fi
        if [[ "$HAVE_WRK" == "false" ]]; then
            log "Installing wrk..."
            # Try apt first; build from source if not available
            sudo apt-get install -y -q wrk 2>/dev/null && HAVE_WRK=true || {
                log "wrk not in apt — building from source..."
                sudo apt-get install -y -q build-essential libssl-dev git
                git clone --quiet --depth 1 https://github.com/wg/wrk /tmp/wrk_src
                make -C /tmp/wrk_src -j"$(nproc)"
                sudo cp /tmp/wrk_src/wrk /usr/local/bin/wrk
                rm -rf /tmp/wrk_src
                HAVE_WRK=true
            }
        fi
        if [[ "$HAVE_LOCUST" == "false" ]]; then
            log "Installing locust and pyotp..."
            pip3 install --quiet locust pyotp; HAVE_LOCUST=true
        fi
    else
        # macOS / non-Debian — just warn
        [[ "$HAVE_AB"     == "false" ]] && warn "ab not found      (macOS: brew install httpd)"
        [[ "$HAVE_WRK"    == "false" ]] && warn "wrk not found     (macOS: brew install wrk)"
        [[ "$HAVE_LOCUST" == "false" ]] && warn "locust not found  (pip3 install locust pyotp)"
    fi

    log "Tools ready: ab=$HAVE_AB  wrk=$HAVE_WRK  locust=$HAVE_LOCUST"
}

# ── Load session cookies ──────────────────────────────────────────────────────
load_session() {
    if [[ ! -f /tmp/armguard_session.env ]]; then
        err "/tmp/armguard_session.env not found.
Run first:
  source <(./scripts/stress-test/auth_session.sh $BASE_URL USERNAME PASSWORD)"
    fi
    # shellcheck source=/dev/null
    source /tmp/armguard_session.env
    log "Session loaded: Cookie=${SESSION_COOKIE:0:24}..."
}

# ── Detect server hardware (via SSH if SERVER_SSH is set, else from known vals) ─
snapshot_metadata() {
    local cpu_count="unknown" ram_gb="unknown" gunicorn_workers="unknown"

    if [[ -n "${SERVER_SSH:-}" ]]; then
        cpu_count=$(ssh "$SERVER_SSH" "nproc 2>/dev/null" 2>/dev/null || echo "unknown")
        ram_gb=$(ssh "$SERVER_SSH" \
            "free -g 2>/dev/null | awk '/^Mem:/{print \$2}'" 2>/dev/null || echo "unknown")
        gunicorn_workers=$(ssh "$SERVER_SSH" \
            "grep GUNICORN_WORKERS /etc/gunicorn/workers.env 2>/dev/null | cut -d= -f2 \
             || ps aux | grep gunicorn | grep -v grep | wc -l" 2>/dev/null || echo "unknown")
    fi

    cat > "$OUTPUT_DIR/metadata.json" <<EOF
{
  "timestamp":          "$TIMESTAMP",
  "server_ip":          "$SERVER_IP",
  "server_protocol":    "$SERVER_PROTOCOL",
  "load_generator_ip":  "$LOAD_GENERATOR_IP",
  "db_engine":          "$DB_ENGINE",
  "conn_max_age":       $CONN_MAX_AGE,
  "logical_cpus":       "$cpu_count",
  "ram_gb":             "$ram_gb",
  "gunicorn_workers":   "$gunicorn_workers",
  "dry_run":            $DRY_RUN
}
EOF
    log "Metadata saved → $OUTPUT_DIR/metadata.json"
}

# ── Start remote resource monitor via SSH (optional) ─────────────────────────
start_remote_monitor() {
    if [[ -z "${SERVER_SSH:-}" ]]; then
        warn "SERVER_SSH not set — skipping remote resource monitoring."
        warn "To enable: export SERVER_SSH=armguard@192.168.0.11"
        return
    fi

    log "Starting monitor_resources.sh on $SERVER_SSH..."
    # Copy the monitor script to the server, then launch it in the background
    scp -q "$SCRIPT_DIR/monitor_resources.sh" "${SERVER_SSH}:/tmp/armguard_monitor_resources.sh" 2>/dev/null || {
        warn "Could not copy monitor_resources.sh to server. Skipping monitoring."
        return
    }
    ssh "$SERVER_SSH" \
        "chmod +x /tmp/armguard_monitor_resources.sh && \
         nohup /tmp/armguard_monitor_resources.sh /tmp/armguard_resources.csv \
         > /tmp/armguard_monitor.log 2>&1 &"
    log "Remote monitor started."
}

# ── Stop remote monitor and retrieve CSV ─────────────────────────────────────
stop_remote_monitor() {
    [[ -z "${SERVER_SSH:-}" ]] && return

    log "Stopping remote monitor..."
    ssh "$SERVER_SSH" "pkill -f armguard_monitor_resources.sh 2>/dev/null; true" 2>/dev/null || true

    log "Fetching resources.csv from server..."
    scp -q "${SERVER_SSH}:/tmp/armguard_resources.csv" \
        "$OUTPUT_DIR/resources.csv" 2>/dev/null \
        && log "resources.csv saved." \
        || warn "Could not retrieve resources.csv (monitor may not have run)."

    # Clean up temp files on server
    ssh "$SERVER_SSH" \
        "rm -f /tmp/armguard_resources.csv /tmp/armguard_monitor_resources.sh /tmp/armguard_monitor.log" \
        2>/dev/null || true
}

# ── Evaluate pass/fail thresholds at each concurrency level ───────────────────
# Returns 0 for PASS/WARN, 1 for FAIL.
evaluate_level() {
    local level="$1"
    local err_pct="${2:-0}"   # error rate as percentage string, e.g. "0.50"
    local p95="${3:-0}"       # p95 latency in ms
    local p99="${4:-0}"       # p99 latency in ms
    local had_5xx="${5:-false}"

    local status="PASS"

    # ── FAIL conditions (stop escalation) ────────────────────────────────────
    if awk "BEGIN{exit !($err_pct > 1)}"; then
        fail "[$level users] Error rate ${err_pct}% > 1% — FAIL"; return 1
    fi
    if (( p95 > 2000 )); then
        fail "[$level users] p95 ${p95}ms > 2000ms — FAIL"; return 1
    fi
    if (( p99 > 5000 )); then
        fail "[$level users] p99 ${p99}ms > 5000ms — FAIL"; return 1
    fi
    if [[ "$had_5xx" == "true" ]]; then
        fail "[$level users] HTTP 502/503 detected — FAIL"; return 1
    fi

    # ── WARNING conditions (continue but flag) ────────────────────────────────
    if awk "BEGIN{exit !($err_pct > 0.1)}"; then
        warn "[$level users] Error rate ${err_pct}% (0.1–1%) — WARNING"; status="WARN"
    fi
    if (( p95 > 1000 )); then
        warn "[$level users] p95 ${p95}ms (1000–2000ms) — WARNING"; status="WARN"
    fi

    ok "[$level users] Status=$status  errors=${err_pct}%  p95=${p95}ms  p99=${p99}ms"
    return 0
}

# ── Parse locust stats CSV, emit error_pct p95 p99 ───────────────────────────
# Locust CSV column order (1-indexed in awk):
# 1=Type 2=Name 3=Requests 4=Failures 5=Median 6=Average 7=Min 8=Max
# 9=Size 10=RPS 11=FailRPS 12=p50 ... 18=p95 ... 20=p99
parse_locust_csv() {
    local csv_file="$1"
    local err_pct=0 p95=0 p99=0

    if [[ ! -f "$csv_file" ]]; then
        echo "0 0 0"; return
    fi

    read -r err_pct p95 p99 < <(awk -F',' '
        $2 == "Aggregated" {
            total   = $3+0
            failed  = $4+0
            pct     = (total > 0) ? (failed*100/total) : 0
            p95val  = $18+0
            p99val  = $20+0
            printf "%.2f %d %d\n", pct, p95val, p99val
            exit
        }
    ' "$csv_file") 2>/dev/null || true

    echo "${err_pct:-0} ${p95:-0} ${p99:-0}"
}

# ── Cleanup handler (runs on EXIT/INT/TERM) ───────────────────────────────────
on_exit() {
    stop_remote_monitor
    echo ""
    log "Test complete. Results in: $OUTPUT_DIR"
}
trap on_exit EXIT INT TERM

# =============================================================================
# MAIN EXECUTION
# =============================================================================

echo ""
log "═══════════════════════════════════════════════════"
log " ArmGuard RDS V1 — Stress Test"
log "═══════════════════════════════════════════════════"
log " Server:         $BASE_URL"
log " Load generator: $LOAD_GENERATOR_IP"
log " DB engine:      $DB_ENGINE  (CONN_MAX_AGE=${CONN_MAX_AGE}s)"
log " Output dir:     $OUTPUT_DIR"
[[ "$DRY_RUN" == "true" ]] && log " Mode:           DRY-RUN"
echo ""

# ── Confirmation prompt (skip in dry-run) ─────────────────────────────────────
if [[ "$DRY_RUN" == "false" ]]; then
    read -r -p "Load will target $SERVER_IP FROM $LOAD_GENERATOR_IP. Continue? [y/N] " CONFIRM
    [[ "${CONFIRM,,}" != "y" ]] && { log "Aborted."; exit 0; }
    echo ""
fi

# ── Setup ──────────────────────────────────────────────────────────────────────
detect_and_install_tools
mkdir -p "$OUTPUT_DIR"
load_session
snapshot_metadata

# ── Determine final concurrency levels ───────────────────────────────────────
LEVELS=("${BASE_LEVELS[@]}")
# Add 500-user level only when server has >= 8 GB RAM
if [[ -n "${SERVER_SSH:-}" ]] && [[ "$DRY_RUN" == "false" ]]; then
    RAM_GB=$(ssh "$SERVER_SSH" "free -g | awk '/^Mem:/{print \$2}'" 2>/dev/null || echo 0)
    if (( RAM_GB >= 8 )); then
        LEVELS+=(500)
        log "RAM >= 8 GB detected — adding 500-user level."
    fi
fi

# ── Start remote resource monitoring ──────────────────────────────────────────
[[ "$DRY_RUN" == "false" ]] && start_remote_monitor

# ── Warm-up: 20 requests at concurrency 1 ────────────────────────────────────
log "Warm-up: 20 requests at concurrency 1 (primes Django caches + DB pool)..."
if [[ "$HAVE_AB" == "true" ]]; then
    run_cmd timeout 120 ab \
        -n 20 -c 1 \
        -H "Cookie: ${AUTH_COOKIE_HEADER}" \
        "${BASE_URL}/dashboard/" \
        > "$OUTPUT_DIR/warmup_ab.txt" 2>&1 || true
elif [[ "$HAVE_WRK" == "true" ]]; then
    run_cmd timeout 30 wrk \
        -t1 -c1 -d5s \
        -H "Cookie: ${AUTH_COOKIE_HEADER}" \
        "${BASE_URL}/dashboard/" \
        > "$OUTPUT_DIR/warmup_wrk.txt" 2>&1 || true
fi

log "Warm-up done. Waiting 10 seconds..."
[[ "$DRY_RUN" == "false" ]] && sleep 10

# ── Incremental concurrency levels ───────────────────────────────────────────
for LEVEL in "${LEVELS[@]}"; do
    [[ "$STOP_ESCALATION" == "true" ]] && break

    echo ""
    log "─────────────────────────────────────────────"
    log " Concurrency level: $LEVEL users"
    log "─────────────────────────────────────────────"

    # ── Tier 1: Static assets (no auth, wrk) ──────────────────────────────────
    STATIC_URL="${BASE_URL}/static/css/main.css"
    log "  [static] wrk -t2 -c${LEVEL} -d30s $STATIC_URL"
    if [[ "$HAVE_WRK" == "true" ]]; then
        run_cmd timeout 120 wrk \
            -t2 -c"${LEVEL}" -d30s \
            --latency \
            "$STATIC_URL" \
            > "$OUTPUT_DIR/wrk_static_c${LEVEL}.txt" 2>&1 || true
    fi

    # ── Tier 2: Public (login page, ab + wrk, no auth) ────────────────────────
    LOGIN_URL="${BASE_URL}/accounts/login/"
    log "  [public] ab -n100000 -c${LEVEL} -t 30 $LOGIN_URL"
    if [[ "$HAVE_AB" == "true" ]]; then
        run_cmd timeout 120 ab \
            -n 100000 -c "${LEVEL}" -t 30 \
            "$LOGIN_URL" \
            > "$OUTPUT_DIR/ab_public_c${LEVEL}.txt" 2>&1 || true
    fi

    # ── Tier 3: Authenticated pages (locust with think time 1–3 s) ───────────
    log "  [auth]   locust -u${LEVEL} --run-time 30s → /dashboard/ /transactions/ /print/reprint-tr/"
    if [[ "$HAVE_LOCUST" == "true" ]]; then
        # Spawn rate: ramp up 5 users/second (avoids thundering herd at high levels)
        SPAWN_RATE=$(( LEVEL > 5 ? 5 : LEVEL ))
        run_cmd timeout 120 locust \
            --headless \
            --users "${LEVEL}" \
            --spawn-rate "${SPAWN_RATE}" \
            --run-time 30s \
            --host "$BASE_URL" \
            --locustfile "$SCRIPT_DIR/locustfile.py" \
            --csv "$OUTPUT_DIR/locust_c${LEVEL}" \
            --only-summary \
            > "$OUTPUT_DIR/locust_c${LEVEL}_output.txt" 2>&1 || true
    fi

    # ── Evaluate thresholds ────────────────────────────────────────────────────
    if [[ "$DRY_RUN" == "false" ]] && [[ "$HAVE_LOCUST" == "true" ]]; then
        LOCUST_CSV="$OUTPUT_DIR/locust_c${LEVEL}_stats.csv"
        read -r ERR_PCT P95 P99 < <(parse_locust_csv "$LOCUST_CSV")

        # Check ab output for 502/503 responses
        HAD_5XX=false
        if grep -qE "^Non-2xx responses:" "$OUTPUT_DIR/ab_public_c${LEVEL}.txt" 2>/dev/null; then
            HAD_5XX=true
        fi

        if ! evaluate_level "$LEVEL" "$ERR_PCT" "$P95" "$P99" "$HAD_5XX"; then
            fail "Stopping at level $LEVEL — threshold breached."
            STOP_ESCALATION=true
        fi
    else
        log "  (threshold evaluation skipped in dry-run mode)"
    fi

    # ── Cooldown between levels ────────────────────────────────────────────────
    if [[ "$STOP_ESCALATION" == "false" ]]; then
        log "  Cooldown: 15 seconds..."
        [[ "$DRY_RUN" == "false" ]] && sleep 15
    fi
done

echo ""
log "Load tests complete."

# ── Run analysis report ───────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "false" ]]; then
    log "Running analyse_results.sh..."
    bash "$SCRIPT_DIR/analyse_results.sh" "$OUTPUT_DIR" 2>&1 | tee "$OUTPUT_DIR/report.txt" || \
        warn "Analysis script returned an error — check $OUTPUT_DIR manually."
else
    log "[DRY-RUN] Would run: bash $SCRIPT_DIR/analyse_results.sh $OUTPUT_DIR"
fi
