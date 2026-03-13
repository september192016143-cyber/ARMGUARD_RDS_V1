#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Stress Test Report Analyser
# =============================================================================
# Parses all ab, wrk, and locust output files in the given results directory
# and produces a unified human-readable report.
#
# Usage:
#   bash scripts/stress-test/analyse_results.sh ~/armguard-stress-results/2026-03-13_14-00
#
# Outputs the report to stdout (stress_test.sh tees it to report.txt).
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { printf "${GREEN}%-8s${NC}" "✅ PASS"; }
warn() { printf "${YELLOW}%-8s${NC}" "⚠️  WARN"; }
fail() { printf "${RED}%-8s${NC}" "❌ FAIL"; }

# ── Arguments ─────────────────────────────────────────────────────────────────
OUTPUT_DIR="${1:-}"
if [[ -z "$OUTPUT_DIR" || ! -d "$OUTPUT_DIR" ]]; then
    echo "Usage: $0 <results-directory>" >&2
    exit 1
fi

META="$OUTPUT_DIR/metadata.json"

# ── Read metadata.json (produced by stress_test.sh) ──────────────────────────
read_meta() {
    local key="$1"
    if command -v python3 &>/dev/null && [[ -f "$META" ]]; then
        python3 -c "
import json, sys
try:
    d = json.load(open('$META'))
    print(d.get('$key', 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null
    else
        echo "unknown"
    fi
}

SERVER_IP=$(read_meta server_ip)
LOAD_GEN=$(read_meta load_generator_ip)
CPU_CORES=$(read_meta logical_cpus)
RAM_GB=$(read_meta ram_gb)
GUNICORN_WORKERS=$(read_meta gunicorn_workers)
DB_ENGINE=$(read_meta db_engine)
CONN_MAX_AGE=$(read_meta conn_max_age)
TIMESTAMP=$(read_meta timestamp)

# ── Parse helpers ─────────────────────────────────────────────────────────────

# ab output: extract Requests/sec, mean latency, failed requests
# Returns: rps p50 err_count
parse_ab() {
    local file="$1"
    [[ ! -f "$file" ]] && echo "0 0 0" && return
    local rps p50 failed
    rps=$(grep    "^Requests per second:" "$file" 2>/dev/null \
          | awk '{printf "%d", $4}') || rps=0
    p50=$(grep    "^Time per request:" "$file" 2>/dev/null \
          | head -1 | awk '{printf "%d", $4}') || p50=0
    failed=$(grep "^Failed requests:" "$file" 2>/dev/null \
          | awk '{print $3}') || failed=0
    echo "${rps:-0} ${p50:-0} ${failed:-0}"
}

# wrk output (--latency mode): extract Req/Sec, p95, p99, errors
# Returns: rps p95 p99 err_count
parse_wrk() {
    local file="$1"
    [[ ! -f "$file" ]] && echo "0 0 0 0" && return
    local rps p95 p99 errs
    rps=$(grep     "Requests/sec:" "$file" 2>/dev/null \
          | awk '{printf "%d", $2}') || rps=0
    # wrk --latency prints percentile lines like:   95.000%    1.23s
    p95=$(grep     "95\." "$file" 2>/dev/null \
          | awk '{v=$2; if(v ~ /ms/) {gsub(/ms/,"",v); printf "%d",v} \
                        else if(v ~ /s$/) {gsub(/s/,"",v); printf "%d",v*1000} \
                        else printf "%d",v}') || p95=0
    p99=$(grep     "99\." "$file" 2>/dev/null \
          | awk '{v=$2; if(v ~ /ms/) {gsub(/ms/,"",v); printf "%d",v} \
                        else if(v ~ /s$/) {gsub(/s/,"",v); printf "%d",v*1000} \
                        else printf "%d",v}') || p99=0
    # wrk prints "X requests in Y, Z non-2xx or 3xx responses" for errors
    errs=$(grep -i "non-2xx"    "$file" 2>/dev/null \
          | awk '{print $1}') || errs=0
    echo "${rps:-0} ${p95:-0} ${p99:-0} ${errs:-0}"
}

# locust CSV (stats.csv): extract RPS, p50, p95, p99, failures
# CSV columns (1-indexed):
#   1=Type 2=Name 3=Requests 4=Failures 5=Median 6=Average 7=Min 8=Max
#   9=AvgSize 10=RPS 11=FailRPS 12=p50 13=p66 14=p75 15=p80 16=p90
#   17=p95 18=p98 19=p99 20=p99.9 21=p99.99 22=p100
# The "Aggregated" row summarises all endpoints.
parse_locust_csv() {
    local csv="$1"
    [[ ! -f "$csv" ]] && echo "0 0 0 0 0" && return
    awk -F',' '
        $2 == "Aggregated" {
            total  = $3+0
            failed = $4+0
            rps    = int($10+0)
            p50    = int($12+0)
            p95    = int($17+0)
            p99    = int($19+0)
            err_pct = (total > 0) ? (failed*100/total) : 0
            printf "%d %d %d %d %.2f\n", rps, p50, p95, p99, err_pct
            exit
        }
    ' "$csv" 2>/dev/null || echo "0 0 0 0 0"
}

# Status badge: PASS/WARN/FAIL based on thresholds
level_status() {
    local err_pct="$1" p95="$2" p99="$3"
    if awk "BEGIN{exit !($err_pct > 1)}" || \
       (( p95 > 2000 )) || \
       (( p99 > 5000 )); then
        fail; return
    fi
    if awk "BEGIN{exit !($err_pct > 0.1)}" || \
       (( p95 > 1000 )); then
        warn; return
    fi
    ok
}

# ── Detect concurrency levels that were tested ────────────────────────────────
LEVELS=()
for f in "$OUTPUT_DIR"/locust_c*_stats.csv "$OUTPUT_DIR"/ab_public_c*.txt; do
    [[ -f "$f" ]] || continue
    lvl=$(basename "$f" | grep -oE 'c[0-9]+' | tr -d 'c')
    [[ -n "$lvl" ]] && LEVELS+=("$lvl")
done
# Deduplicate and sort numerically
IFS=$'\n' LEVELS=($(printf '%s\n' "${LEVELS[@]}" | sort -nu)); unset IFS

# ── Gunicorn tuning calculation ───────────────────────────────────────────────
if [[ "$CPU_CORES" =~ ^[0-9]+$ ]] && [[ "$RAM_GB" =~ ^[0-9]+$ ]]; then
    RECOMMENDED=$(( CPU_CORES * 2 + 1 ))
    RAM_CAP=$(python3 -c "import math; print(math.floor(($RAM_GB * 1024 - 1024) / 100))" 2>/dev/null || echo "?")
    if [[ "$RAM_CAP" =~ ^[0-9]+$ ]]; then
        FINAL_WORKERS=$(( RECOMMENDED < RAM_CAP ? RECOMMENDED : RAM_CAP ))
    else
        FINAL_WORKERS="$RECOMMENDED"
    fi
else
    RECOMMENDED="(CPUs unknown)"
    FINAL_WORKERS="(CPUs unknown)"
fi

# =============================================================================
# REPORT OUTPUT
# =============================================================================

echo ""
echo "════════════════════════════════════════════════════════════════"
echo " ARMGUARD RDS STRESS TEST REPORT"
echo "════════════════════════════════════════════════════════════════"
printf " Tested:    %s  (from %s)\n" "$SERVER_IP" "$LOAD_GEN"
printf " Timestamp: %s\n" "$TIMESTAMP"
printf " CPU:       %s cores   RAM: %s GB\n" "$CPU_CORES" "$RAM_GB"
printf " Gunicorn:  %s workers   DB: %s (CONN_MAX_AGE=%s)\n" \
       "$GUNICORN_WORKERS" "$DB_ENGINE" "$CONN_MAX_AGE"
echo "────────────────────────────────────────────────────────────────"
echo ""

if [[ ${#LEVELS[@]} -eq 0 ]]; then
    echo " No result files found in: $OUTPUT_DIR"
    echo " Run stress_test.sh first."
    exit 0
fi

printf "%-12s %-8s %-8s %-8s %-8s %-10s %-8s\n" \
       "Level" "RPS" "p50ms" "p95ms" "p99ms" "Errors%" "Status"
printf "%s\n" "──────────────────────────────────────────────────────────"

MAX_STABLE_LEVEL=0
BOTTLENECK=""
FIRST_FAIL=false

for LEVEL in "${LEVELS[@]}"; do
    LOCUST_CSV="$OUTPUT_DIR/locust_c${LEVEL}_stats.csv"

    # Primary data source: locust (most complete)
    read -r RPS P50 P95 P99 ERR_PCT < <(parse_locust_csv "$LOCUST_CSV")

    # Fallback: wrk static output if locust didn't run
    if (( RPS == 0 )); then
        WRK_FILE="$OUTPUT_DIR/wrk_static_c${LEVEL}.txt"
        read -r WRK_RPS WRK_P95 WRK_P99 _ERRS < <(parse_wrk "$WRK_FILE")
        RPS=${WRK_RPS:-0}; P95=${WRK_P95:-0}; P99=${WRK_P99:-0}
    fi

    STATUS_STR=$(level_status "$ERR_PCT" "$P95" "$P99")

    printf "%-12s %-8s %-8s %-8s %-8s %-10s " \
           "${LEVEL} users" "$RPS" "$P50" "$P95" "$P99" "${ERR_PCT}%"
    echo -e "$STATUS_STR"

    # Track maximum stable level
    if awk "BEGIN{exit !($ERR_PCT <= 1)}" && \
       (( P95 <= 2000 )) && \
       (( P99 <= 5000 )); then
        MAX_STABLE_LEVEL=$LEVEL
    else
        if [[ "$FIRST_FAIL" == "false" ]]; then
            FIRST_FAIL=true
            if (( P95 > 2000 )); then
                BOTTLENECK="p95 exceeded 2000ms at ${LEVEL} users"
            elif (( P99 > 5000 )); then
                BOTTLENECK="p99 exceeded 5000ms at ${LEVEL} users"
            elif awk "BEGIN{exit !($ERR_PCT > 1)}"; then
                BOTTLENECK="error rate exceeded 1% at ${LEVEL} users"
            fi
        fi
    fi
done

echo ""
echo "────────────────────────────────────────────────────────────────"
printf " Maximum stable concurrency: %s users\n" "$MAX_STABLE_LEVEL"
[[ -n "$BOTTLENECK" ]] && printf " Bottleneck: %s\n" "$BOTTLENECK"

# ── Gunicorn tuning recommendation ───────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────────────────────────"
echo " Gunicorn Tuning Recommendation"
echo "────────────────────────────────────────────────────────────────"
printf " Formula: (CPUs × 2) + 1 = %s\n" "$RECOMMENDED"
printf " RAM cap: floor((%s GB × 1024 - 1024) / 100) = %s\n" "$RAM_GB" "$RAM_CAP"
printf " Recommended FINAL_WORKERS = %s\n" "$FINAL_WORKERS"
echo ""
echo " Apply to /etc/gunicorn/workers.env:"
printf "   GUNICORN_WORKERS=%s\n" "$FINAL_WORKERS"
printf "   GUNICORN_THREADS=2\n"
echo ""
printf " Django CONN_MAX_AGE (already set to %s — no change needed).\n" "$CONN_MAX_AGE"
echo ""

# ── Resource monitor summary (if CSV present) ─────────────────────────────────
RESOURCES_CSV="$OUTPUT_DIR/resources.csv"
if [[ -f "$RESOURCES_CSV" ]] && (( $(wc -l < "$RESOURCES_CSV") > 1 )); then
    echo "────────────────────────────────────────────────────────────────"
    echo " Server Resource Summary (from monitor_resources.sh)"
    echo "────────────────────────────────────────────────────────────────"
    awk -F',' '
        NR==1 { next }
        {
            cpu_sum  += $2; ram_max  = ($3 > ram_max)  ? $3 : ram_max
            swap_max  = ($4 > swap_max) ? $4 : swap_max
            load_max  = ($5 > load_max) ? $5 : load_max
            count++
        }
        END {
            if (count > 0) {
                printf " Avg CPU:      %.1f%%\n", cpu_sum/count
                printf " Peak RAM:     %d MB\n",  ram_max
                printf " Peak Swap:    %d MB\n",  swap_max
                printf " Peak Load 1m: %.2f\n",   load_max
                printf " Samples:      %d\n",     count
            }
        }
    ' "$RESOURCES_CSV"
    echo ""
fi

echo "════════════════════════════════════════════════════════════════"
echo " Full results: $OUTPUT_DIR"
echo "════════════════════════════════════════════════════════════════"
