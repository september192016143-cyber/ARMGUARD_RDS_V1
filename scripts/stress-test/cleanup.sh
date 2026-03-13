#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Stress Test Post-Test Cleanup
# =============================================================================
# Run this AFTER stress_test.sh completes (or after any failed test run).
# It removes test Django sessions, temp cookie files, and prints a log summary.
#
# Usage (from project root on the SERVER):
#   bash scripts/stress-test/cleanup.sh
#
# Optional env vars:
#   SERVER_SSH    If set, runs Django clearsessions on the server via SSH.
#                 Example: export SERVER_SSH=armguard@192.168.0.11
#   RESULTS_DIR   Base results directory (default: ~/armguard-stress-results)
# =============================================================================

set -euo pipefail

DEPLOY_DIR="/var/www/ARMGUARD_RDS_V1"
VENV_PYTHON="$DEPLOY_DIR/venv/bin/python"
PROJECT_DIR="$DEPLOY_DIR/project"
RESULTS_BASE="${RESULTS_DIR:-${HOME}/armguard-stress-results}"

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${CYAN}[cleanup]${NC} $*"; }
ok()   { echo -e "${GREEN}[cleanup]${NC} $*"; }
warn() { echo -e "${YELLOW}[cleanup]${NC} $*"; }

# =============================================================================
# 1. Remove Django test sessions
#    clearsessions deletes expired sessions from the DB — safe to run anytime.
# =============================================================================
run_clearsessions() {
    log "Running manage.py clearsessions (removes expired sessions from DB)..."
    if [[ -n "${SERVER_SSH:-}" ]]; then
        # Run on the server via SSH
        ssh "$SERVER_SSH" "
            cd '$PROJECT_DIR' &&
            DJANGO_SETTINGS_MODULE=armguard.settings.production \
            '$VENV_PYTHON' manage.py clearsessions &&
            echo 'clearsessions completed.'
        " && ok "Sessions cleared on $SERVER_SSH." \
          || warn "clearsessions failed on $SERVER_SSH — run manually."
    elif [[ -x "$VENV_PYTHON" ]] && [[ -f "$PROJECT_DIR/manage.py" ]]; then
        # Running directly on the server
        cd "$PROJECT_DIR"
        DJANGO_SETTINGS_MODULE=armguard.settings.production \
            "$VENV_PYTHON" manage.py clearsessions \
            && ok "Sessions cleared." \
            || warn "clearsessions failed — run manually: cd $PROJECT_DIR && python manage.py clearsessions"
    else
        warn "Cannot reach server. Run manually:"
        warn "  ssh armguard@192.168.0.11 \"cd $PROJECT_DIR && DJANGO_SETTINGS_MODULE=armguard.settings.production $VENV_PYTHON manage.py clearsessions\""
    fi
}

# =============================================================================
# 2. Remove local temp files
# =============================================================================
remove_temp_files() {
    log "Removing temp authentication files..."
    local removed=0

    for f in \
        /tmp/armguard_session.env \
        /tmp/armguard_login_resp.html \
        /tmp/armguard_otp_resp.html \
        /tmp/armguard_cookies_*
    do
        # Glob may not match anything — skip quietly
        # shellcheck disable=SC2086
        for matched in $f; do
            [[ -f "$matched" ]] || continue
            rm -f "$matched" && (( removed++ )) && ok "Removed: $matched"
        done
    done

    if [[ $removed -eq 0 ]]; then
        log "No temp files found (already clean)."
    fi
}

# =============================================================================
# 3. Print summary of saved log files
# =============================================================================
print_results_summary() {
    log "Results directories:"
    if [[ ! -d "$RESULTS_BASE" ]]; then
        warn "Results base directory not found: $RESULTS_BASE"
        return
    fi

    local total_size
    total_size=$(du -sh "$RESULTS_BASE" 2>/dev/null | awk '{print $1}') || total_size="unknown"

    find "$RESULTS_BASE" -maxdepth 1 -mindepth 1 -type d \
        | sort -r \
        | head -10 \
        | while read -r run_dir; do
            local dir_size
            dir_size=$(du -sh "$run_dir" 2>/dev/null | awk '{print $1}') || dir_size="?"
            local file_count
            file_count=$(find "$run_dir" -type f 2>/dev/null | wc -l) || file_count="?"
            printf "  %-45s  %6s  %d files\n" \
                "$(basename "$run_dir")" "$dir_size" "$file_count"
        done

    echo ""
    ok "Total results size: $total_size  (in $RESULTS_BASE)"
    log "To view the latest report:"
    log "  cat $RESULTS_BASE/\$(ls -t $RESULTS_BASE | head -1)/report.txt"
}

# =============================================================================
# MAIN
# =============================================================================
log "ArmGuard RDS V1 — Post-test cleanup"
echo ""

run_clearsessions
echo ""
remove_temp_files
echo ""
print_results_summary
echo ""
ok "Cleanup complete."
