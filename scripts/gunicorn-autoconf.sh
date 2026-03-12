#!/usr/bin/env bash
# =============================================================================
# ArmGuard RDS V1 — Gunicorn Runtime Auto-Tuner
# =============================================================================
# Install to:  /usr/local/bin/gunicorn-autoconf.sh
# Run as:      root (reads /proc, writes /etc/gunicorn/)
#
# Usage:
#   sudo bash scripts/gunicorn-autoconf.sh          # detect and write workers.env
#   sudo bash scripts/gunicorn-autoconf.sh --dry-run # print without writing
#
# What it does:
#   1. Detects logical CPU count and available RAM at runtime.
#   2. Applies the worker formula: (logical_cpus × 2) + 1.
#   3. Applies RAM safety cap: floor((RAM_MB - 1024) / 100).
#      (Each Gunicorn worker consumes ~100 MB RSS; 1 GB reserved for OS.)
#   4. Determines thread count: 2 for SSD, 4 for HDD.
#   5. Writes results to /etc/gunicorn/workers.env for systemd EnvironmentFile.
#   6. Logs detected values and decisions to /var/log/armguard/gunicorn-autoconf.log.
#
# deploy.sh calls this automatically. Re-run after CPU or RAM hardware changes.
# =============================================================================

set -Eeo pipefail

# ---------------------------------------------------------------------------
# Defaults / configuration
# ---------------------------------------------------------------------------
WORKERS_ENV_DIR="/etc/gunicorn"
WORKERS_ENV_FILE="$WORKERS_ENV_DIR/workers.env"
LOG_DIR="/var/log/armguard"
LOG_FILE="$LOG_DIR/gunicorn-autoconf.log"
DRY_RUN=false

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { local ts; ts=$(date '+%Y-%m-%d %H:%M:%S'); echo -e "${CYAN}[AUTOCONF]${NC} $*"; echo "$ts [AUTOCONF] $*" >> "$LOG_FILE" 2>/dev/null || true; }
warn() { local ts; ts=$(date '+%Y-%m-%d %H:%M:%S'); echo -e "${YELLOW}[WARNING]${NC}  $*"; echo "$ts [WARNING]  $*" >> "$LOG_FILE" 2>/dev/null || true; }
err()  { echo -e "${RED}[ERROR]${NC}   $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h)
            echo "Usage: sudo $0 [--dry-run]"
            echo "  --dry-run  Print computed values without writing workers.env"
            exit 0 ;;
        *) err "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || err "Run as root: sudo $0"

mkdir -p "$LOG_DIR"
log "=== Gunicorn auto-tuning started ==="

# ---------------------------------------------------------------------------
# Step 1: Detect logical CPU count
# ---------------------------------------------------------------------------
LOGICAL_CPUS=$(nproc 2>/dev/null || grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo 1)
log "Detected logical CPUs: $LOGICAL_CPUS"

# ---------------------------------------------------------------------------
# Step 2: Detect available RAM (MB)
# ---------------------------------------------------------------------------
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_MB=$(( RAM_KB / 1024 ))
RAM_GB=$(( RAM_MB / 1024 ))
log "Detected RAM: ${RAM_MB} MB (${RAM_GB} GB)"

# ---------------------------------------------------------------------------
# Step 3: Detect disk type (SSD vs HDD) — affects thread count
# ---------------------------------------------------------------------------
# Find the primary block device (first non-loop, non-dm device).
PRIMARY_DISK=$(lsblk -d -n -o NAME,TYPE 2>/dev/null \
    | grep -v 'loop\|rom\|ram' \
    | head -1 \
    | awk '{print $1}')

DISK_ROTA=1  # default: HDD
if [[ -n "$PRIMARY_DISK" && -r "/sys/block/$PRIMARY_DISK/queue/rotational" ]]; then
    DISK_ROTA=$(cat "/sys/block/$PRIMARY_DISK/queue/rotational")
fi

if [[ "$DISK_ROTA" -eq 0 ]]; then
    DISK_TYPE="SSD"
    THREADS=2
else
    DISK_TYPE="HDD"
    THREADS=4
fi
log "Detected disk type: $DISK_TYPE (ROTA=$DISK_ROTA) → THREADS=$THREADS"

# ---------------------------------------------------------------------------
# Step 4: Compute worker count
# ---------------------------------------------------------------------------
# Base formula: (logical_cpus × 2) + 1
WORKERS_BASE=$(( LOGICAL_CPUS * 2 + 1 ))

# RAM safety cap: each worker uses ~100 MB; reserve 1 GB for OS and other
# processes. Cap = floor((RAM_MB - 1024) / 100).
# If RAM ≤ 1024 MB, cap at 1 (absolute minimum).
if [[ "$RAM_MB" -gt 1024 ]]; then
    RAM_CAP=$(( (RAM_MB - 1024) / 100 ))
else
    RAM_CAP=1
fi

# Hard minimum of 1, hard maximum of 32 (sanity guard).
[[ "$RAM_CAP" -lt 1 ]] && RAM_CAP=1
[[ "$RAM_CAP" -gt 32 ]] && RAM_CAP=32

# Apply RAM cap and low-RAM override
if [[ "$RAM_GB" -lt 4 ]]; then
    WORKERS=3
    warn "RAM < 4 GB (${RAM_GB} GB detected) — capping WORKERS at 3 to prevent OOM."
elif [[ "$WORKERS_BASE" -gt "$RAM_CAP" ]]; then
    WORKERS=$RAM_CAP
    warn "Workers formula ($WORKERS_BASE) exceeds RAM cap ($RAM_CAP) — using RAM cap."
else
    WORKERS=$WORKERS_BASE
fi

log "Worker formula: (${LOGICAL_CPUS} × 2) + 1 = ${WORKERS_BASE} | RAM cap: ${RAM_CAP} | Final WORKERS=${WORKERS}"
log "Final: WORKERS=$WORKERS  THREADS=$THREADS  DISK=$DISK_TYPE"

# ---------------------------------------------------------------------------
# Step 5: Report and write
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}┌─────────────────────────────────────────[AUTOCONF]─────┐${NC}"
echo -e "${BOLD}│  Logical CPUs : ${LOGICAL_CPUS}${NC}"
echo -e "${BOLD}│  RAM          : ${RAM_MB} MB (${RAM_GB} GB)${NC}"
echo -e "${BOLD}│  Disk type    : ${DISK_TYPE}${NC}"
echo -e "${BOLD}│  WORKERS      : ${WORKERS}  (formula: (${LOGICAL_CPUS}×2)+1=${WORKERS_BASE}, cap=${RAM_CAP})${NC}"
echo -e "${BOLD}│  THREADS      : ${THREADS}${NC}"
echo -e "${BOLD}└────────────────────────────────────────────────────────┘${NC}"
echo

if [[ "$DRY_RUN" == "true" ]]; then
    echo "# DRY RUN — would write to $WORKERS_ENV_FILE:"
    echo "GUNICORN_WORKERS=$WORKERS"
    echo "GUNICORN_THREADS=$THREADS"
    echo "# (disk: $DISK_TYPE, RAM cap: $RAM_CAP, logical cpus: $LOGICAL_CPUS)"
    log "Dry-run complete — $WORKERS_ENV_FILE NOT written."
    exit 0
fi

# Create directory and write env file
mkdir -p "$WORKERS_ENV_DIR"
chmod 755 "$WORKERS_ENV_DIR"

cat > "$WORKERS_ENV_FILE" <<EOF
# Generated by gunicorn-autoconf.sh on $(date '+%Y-%m-%d %H:%M:%S')
# Logical CPUs: $LOGICAL_CPUS  |  RAM: ${RAM_MB} MB  |  Disk: $DISK_TYPE
# Re-run: sudo /usr/local/bin/gunicorn-autoconf.sh
GUNICORN_WORKERS=$WORKERS
GUNICORN_THREADS=$THREADS
EOF

chmod 640 "$WORKERS_ENV_FILE"
log "Written: $WORKERS_ENV_FILE"
log "=== Auto-tuning complete ==="

echo -e "${GREEN}[OK]${NC}    workers.env written to $WORKERS_ENV_FILE"
echo "      Reload Gunicorn to apply: sudo systemctl reload armguard-gunicorn"
