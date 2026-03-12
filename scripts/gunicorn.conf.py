# =============================================================================
# ArmGuard RDS V1 — Gunicorn Configuration File
# =============================================================================
# Reference: https://docs.gunicorn.org/en/stable/settings.html
#
# Worker counts are read from /etc/gunicorn/workers.env at runtime,
# written there by gunicorn-autoconf.sh. This file provides sane fallbacks
# if that env file has not been generated yet.
#
# Run the auto-tuner once at deploy time (deploy.sh does this automatically):
#   sudo /usr/local/bin/gunicorn-autoconf.sh
#
# Regenerate after hardware changes (CPU/RAM upgrade):
#   sudo /usr/local/bin/gunicorn-autoconf.sh && sudo systemctl restart armguard-gunicorn
# =============================================================================

import multiprocessing
import os

# ── Worker count ─────────────────────────────────────────────────────────────
# Formula: (logical_cpus × 2) + 1, capped by RAM (1 worker ≈ 100 MB RSS).
# Override via GUNICORN_WORKERS env var (set by gunicorn-autoconf.sh).
_cpus = multiprocessing.cpu_count()
workers = int(os.environ.get("GUNICORN_WORKERS", (_cpus * 2) + 1))

# ── Worker class ─────────────────────────────────────────────────────────────
# gthread: each worker spawns THREADS green threads.
# Better than 'sync' for I/O-bound Django apps (DB queries, file reads).
# Better than 'gevent' for pure-WSGI Django (no async complications).
worker_class = "gthread"

# ── Thread count ─────────────────────────────────────────────────────────────
# SSD: 2 threads (I/O is fast, threads add CPU overhead).
# HDD: 4 threads (threads absorb disk-wait latency).
# Override via GUNICORN_THREADS (set by gunicorn-autoconf.sh).
threads = int(os.environ.get("GUNICORN_THREADS", 2))

# ── Timeouts ─────────────────────────────────────────────────────────────────
# 120 s prevents spurious WORKER TIMEOUT kills on slow DB queries or large
# report generation. Gunicorn logs a CRITICAL warning at exactly this value.
timeout = 120
graceful_timeout = 30  # seconds a worker has to finish in-flight requests on HUP

# ── Keep-alive ───────────────────────────────────────────────────────────────
# Nginx keepalive 8 upstream matches this; eliminates a TCP handshake per request.
keepalive = 5

# ── Worker recycling ─────────────────────────────────────────────────────────
# Recycle workers every 1000 requests (±100 jitter) to prevent memory leaks
# in long-running Python processes.
max_requests = 1000
max_requests_jitter = 100

# ── Binding ───────────────────────────────────────────────────────────────────
# Override GUNICORN_BIND to use a Unix socket for lower latency:
#   GUNICORN_BIND=unix:/run/armguard/gunicorn.sock
# Default: TCP on loopback (simpler, works without socket directory setup).
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = "/var/log/armguard/gunicorn-access.log"
errorlog  = "/var/log/armguard/gunicorn.log"
loglevel  = "info"
capture_output = True  # redirect print() / uncaught exceptions to errorlog

# ── Process naming ────────────────────────────────────────────────────────────
# Visible in ps/top as 'armguard-v1 [worker 1]' etc.
proc_name = "armguard-v1"

# ── Security ─────────────────────────────────────────────────────────────────
# Defend against slow-header attacks / oversized request lines.
limit_request_line   = 4094
limit_request_fields = 100
limit_request_field_size = 8190
