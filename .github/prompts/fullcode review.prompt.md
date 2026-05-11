---
name: fullcode review
description: Full code review of ARMGUARD_RDS_V1 — structure, architecture, quality, security, performance, testing, dependencies, data structure, deployment config, migrations, logging, backup, static/media, frontend JS, SSL/TLS, and error handling. Run before a major release or after a large feature merge.
applyTo: "**"
---

You are a senior software engineer performing a full code review of the **ARMGUARD_RDS_V1** Django application.

**Project context:**
- Stack: Django 6.0.3 + Gunicorn (gthread) + Nginx + Ubuntu 24.04 LTS (bare-metal systemd, no Docker)
- Database: PostgreSQL
- Deploy path: `/var/www/ARMGUARD_RDS_V1`
- Key directories: `armguard/` (Django apps), `scripts/` (deploy/backup/update), `templates/`, `static/`

**Rules — enforce these for every section:**
1. **Read the actual files** before commenting — do not give generic advice without citing specific file paths or line numbers.
2. For each issue found, state: what file, what line/function, what the problem is, and what the fix is.
3. Skip any sub-item where no problem exists — write "No issues found."
4. Do not invent problems. Only report what you actually see in the code.

---

### 1. Project & Folder Structure
- Is separation of concerns maintained across apps, templates, static, and scripts?
- Are there redundant, misplaced, or poorly named files?
- Would a new developer be able to orient themselves quickly?

### 2. Architecture & Design Patterns
- Are the chosen frameworks, libraries, and patterns appropriate for this scale?
- Is there anything that should be simplified or that violates Django conventions?
- **Verify**: `apps/transactions/signals.py:on_transaction_save` and `apps/transactions/services.py:write_audit_entry` — confirm only **one** path writes an `AuditLog` row per `Transaction.save()`. A prior review found both active simultaneously, producing duplicate entries per save.

### 3. Code Quality
- Readability, naming conventions, indentation consistency.
- Duplicate logic, dead code, or unnecessary complexity.
- Are views, forms, and models following Django best practices?

### 4. Security
- SQL injection, XSS, CSRF, insecure authentication, broken access control.
- Data validation, input sanitization, permission checks on every view.
- Hardcoded secrets, exposed credentials, unsafe settings.
- **Verify**: `apps/camera/views.py:_client_ip()` — must use `split(',')[-1].strip()` (last `X-Forwarded-For` entry, appended by Nginx, trustworthy). A prior review found `[0]` (first entry, client-controlled, spoofable). The correct pattern is already used in `middleware/activity.py` and `apps/users/models.py`.
- **Verify**: `templates/registration/login.html` — confirm there is no `<link>` tag loading FontAwesome from a CDN (e.g. `cdnjs.cloudflare.com`) without a `integrity=` SRI attribute. FontAwesome is self-hosted at `static/css/fontawesome/`; a redundant CDN load with no SRI is a supply-chain risk.

### 5. Performance
- N+1 query patterns, missing `select_related`/`prefetch_related`.
- Unindexed foreign keys or filter fields on large tables.
- Heavy template logic or synchronous blocking calls.

### 6. Testing & Reliability
- Test file locations and coverage (what is tested vs. what is not).
- Error handling: are exceptions caught and logged appropriately?
- Any silent failure paths or missing `try/except` on I/O operations.

### 7. Dependencies & Environment
- `requirements.txt`: pinned versions, known CVEs, unused packages. **Five packages are historically loose-pinned with `>=`**: `drf-spectacular`, `psycopg2-binary`, `redis`, `gspread`, `google-auth` — verify each is now pinned to an exact version.
- `.env.example`: are all required vars documented?
- Any dev-only packages that could accidentally reach production.
- **Verify** `.github/workflows/ci.yml`: the `working-directory` on the install and test steps must match the actual repo structure. A prior review found the hardcoded path `final/ARMGUARD_RDS_V1/project` which does not exist in any clone — the CI pipeline was effectively never running. Confirm the path now resolves correctly and that `pip-audit` is scanning the right `requirements.txt`.

### 8. Data Structure
- Review all Django models across every app for field choices, data types, constraints, and default values.
- Are `ForeignKey` / `OneToOneField` / `ManyToManyField` relationships correct and using appropriate `on_delete` policies?
- Are indexes defined on all fields used in `filter()`, `order_by()`, or `JOIN` conditions on large tables?
- Are there missing `unique_together` / `UniqueConstraint` / `CheckConstraint` where business rules require uniqueness or value ranges?
- Are nullable fields (`null=True`, `blank=True`) used intentionally, or are they masking missing data?
- Are there any fields that store structured data (JSON, comma-separated values) that should instead be a related model?
- Does the schema reflect the actual business domain accurately (correct naming, no ambiguous fields)?

### 9. Deployment Configuration
- Read `scripts/gunicorn.conf.py`: worker count comes from the `GUNICORN_WORKERS` env var (default `(cpu_count() * 2) + 1`), written at boot by `scripts/gunicorn-autoconf.sh` into `/etc/gunicorn/workers.env`. Verify the auto-tune logic is correct for the target CPU count. Worker class is `gthread` — are `workers` × `threads` within the PostgreSQL connection-pool budget?
- **Check the `max_requests` conflict**: `scripts/gunicorn.conf.py` sets `max_requests = 0` (disabled, to protect long-running OREX simulation threads from mid-request worker recycles). However, `scripts/armguard-gunicorn.service` passes `--max-requests 1000 --max-requests-jitter 100` in `ExecStart`. CLI args win over the config file — workers ARE recycled every ~1000 requests. This can kill live OREX threads. Is this conflict intentional?
- Read `scripts/nginx-armguard.conf` (HTTP) and `scripts/nginx-armguard-ssl-lan.conf` (SSL): verify `proxy_set_header` directives cover `X-Forwarded-For`, `X-Real-IP`, and `X-Forwarded-Proto`. Check the `.mjs` regex location — does it correctly serve `application/javascript` MIME type without overriding the global MIME table? Are the `__DOMAIN__`, `__LAN_IP__`, `__STATIC_ROOT__`, `__MEDIA_ROOT__` placeholders all substituted by `scripts/deploy.sh`?
- Read `scripts/armguard-gunicorn.service`: confirm `Type=notify`, `EnvironmentFile=__DEPLOY_DIR__/.env`, secondary `EnvironmentFile=-/etc/gunicorn/workers.env`, `Restart=on-failure RestartSec=5`, and `ExecReload=/bin/kill -s HUP $MAINPID` (zero-downtime HUP). Are `__DEPLOY_USER__` and `__DEPLOY_DIR__` placeholders substituted correctly?
- Read `scripts/deploy.sh` and `scripts/update-server.sh`: confirm both run `migrate` then `collectstatic` then a graceful HUP reload in the correct order. Does `scripts/update-server.sh` take a pre-update backup before running `migrate`?

### 10. Database Migrations
- Run `python manage.py makemigrations --check` to confirm no un-generated migrations exist.
- There are **5 `RunPython` migrations** in this repo: `inventory/0003_seed_magazine_pools.py`, `personnel/0004_personnelgroup.py`, `transactions/0005_backfill_tr_return_by.py`, `users/0019_auto_print_tr_per_purpose.py`, `users/0029_fix_activitylog_index_names.py`. For each one, verify it defines a `reverse_func` (or explicitly passes `atomic=False` with a documented reason).
- There are **2 `RunSQL` migrations**: `inventory/0016_emtan_capacity_fix.py` and `users/0026_systemsettings_rifle_magazine_default_limit.py`. Verify each provides reversal SQL or explicitly passes `reverse_sql=migrations.RunSQL.noop`.
- Are there any migrations that drop or rename columns? If so, do they follow a multi-step zero-downtime strategy (add nullable → backfill → constrain → drop old column)?
- The `users` app has 32 migrations (latest: `0032_simulationrun.py`). Consider squashing to reduce load on fresh deployments.
- Confirm `scripts/update-server.sh` takes a database backup before running `migrate`. Verify the backup step precedes `python manage.py migrate`.

### 11. Logging & Observability
- Read `settings/base.py` `LOGGING` config (~line 370): it uses `QueueHandler`/`QueueListener` for async log dispatch to a rotating file at `project/logs/armguard.log` (10 MB, 5 backups). Verify `LOG_DIR.mkdir(exist_ok=True)` runs at settings import time before the first request is handled.
- Log levels: file handler = INFO, console = WARNING, `django.request` logger = ERROR, `django.security` = WARNING. Is ERROR correct for `django.request`? This silences all 4xx client errors in the file log — is that intentional?
- Gunicorn writes separate logs to `/var/log/armguard/gunicorn.log` (errors) and `/var/log/armguard/gunicorn-access.log`. SSL renewal writes to `/var/log/armguard/ssl-renewal.log`. Verify these paths match the `logrotate` config installed by `scripts/deploy.sh`.
- **No `/health/` or `/ping/` endpoint exists** (`armguard/urls.py` and `apps/dashboard/urls.py` have no match). Without a health probe, the systemd watchdog and any external monitors consider the service healthy as long as the process is alive, even if Django is deadlocked. Add a minimal unauthenticated endpoint.
- **`SENTRY_DSN` is documented in `.env.example` but never consumed** — neither `settings/base.py` nor `settings/production.py` calls `sentry_sdk.init()`. Setting the env var has no effect; 500-level errors are never forwarded. Either wire it up (install `sentry-sdk`, call `init()` in `settings/production.py` when `SENTRY_DSN` is set) or remove the documented var to avoid false expectations.

### 12. Backup & Recovery
- Read `scripts/backup.sh`: it backs up the SQLite DB (Django management command hot-copy), the `media/` directory, and `.env`. Local path: `/var/backups/armguard/YYYYMMDD_HHMMSS/`. Mirror: `/mnt/backup/armguard/` (external drive UUID `ff28a2b1-...`). Is mount failure handled gracefully, or does a missing external drive silently skip the off-site copy?
- GPG encryption (`ARMGUARD_BACKUP_GPG_RECIPIENT`) is optional in `scripts/backup.sh`. If the env var is unset, backups containing `.env` (with `DJANGO_SECRET_KEY` and DB credentials) are stored in plaintext. Is this acceptable for the deployment environment?
- Read `scripts/db-backup-cron.sh`: verify it does not duplicate logic from `backup.sh` or write to a conflicting location.
- Retention is 7 days. Is that long enough to detect a silent data-corruption event before all good backups are pruned?
- `scripts/retrieve-backup.sh` and `docs/BACKUP_DOCUMENTATION.md` / `docs/BACKUP_INSTRUCTIONS.md` exist. Has the restore procedure been tested end-to-end to confirm it produces a working application?

### 13. Static Files & Media
- `scripts/deploy.sh` and `scripts/update-server.sh` both run `collectstatic` before reloading Gunicorn. Confirm the order: `migrate` → `collectstatic` → `kill -HUP`. Static files must be ready before new workers serve requests.
- Production uses `ArmguardStaticStorage` (defined in `armguard/storage.py`), which extends WhiteNoise's `CompressedManifestStaticFilesStorage` and skips URL-rewriting for `.mjs` files. Verify the subclass does not break cache-busting hash suffixes for non-`.mjs` assets.
- Nginx serves `.mjs` files via a dedicated regex location (`~* "^/static/(.+\.mjs)$"`) with an isolated `types{}` block. This location is present in **both** `scripts/nginx-armguard-ssl-lan.conf` and `scripts/nginx-armguard.conf` (HTTP variant). Verify future edits keep both in sync — divergence here causes `.mjs` modules to 404 or get served as `application/octet-stream` on one variant.
- Is `MEDIA_ROOT` configured in Nginx with `autoindex off` and without script execution (no `fastcgi_pass` or `proxy_pass` under the media location)? Media uploads (personnel images, QR codes, serial images) must not be served as executable.
- Is `client_max_body_size 20M` (set in both Nginx configs) sufficient for the largest expected personnel image or serial capture photo?

### 14. Frontend JavaScript
- There are 34 `.js` files under `static/js/`. No `eval()` or `document.write()` calls were found. `innerHTML` assignments appear in at least 6 files: `base.js` (lines 236, 402, 789, 798), `calendar_widget.js`, `camera_devices.js`, `camera_pair.js`, `dashboard_tables.js` (lines 49, 88, 123, 161), and `dashboard_sim_status.js` (line 136). For each assignment of the form `body.innerHTML = html` where `html` is assembled from an API response, confirm the data is numeric/date-only or explicitly sanitized before insertion.
- `fetch()` is used in `ammunition_list.js`. Verify it includes the CSRF token (`X-CSRFToken` header via `getCookie('csrftoken')`) on any non-GET request.
- CSRF token utilities are present in `camera_devices.js`, `camera_pair.js`, `dashboard_sim_status.js`, `discrepancy_phone_capture.js`, `idle_timeout.js`, and `item_form.js`. Verify every file that issues a mutating request (POST/PUT/DELETE) is in this list.
- No hardcoded `http://` or `https://` URLs were found in any JS file. Confirm API endpoint paths are injected via `data-*` attributes or Django's `{% url %}` tag rather than JS string literals.
- Are any of the 34 JS files unreferenced by any template? Dead JS files increase the attack surface and should be removed.

### 15. SSL/TLS & Certificate Management
- `scripts/nginx-armguard-ssl-lan.conf`: protocols are `TLSv1.2 TLSv1.3` (TLS 1.0/1.1 correctly disabled). Ciphers are ECDHE-ECDSA/RSA AES128/256-GCM only (AEAD, no weak suites). DHparam is at `/etc/ssl/certs/dhparam.pem` — verify it is at least 2048-bit (4096 recommended).
- **Double HSTS**: Nginx adds `Strict-Transport-Security: max-age=31536000; includeSubDomains` in `nginx-armguard-ssl-lan.conf` AND `settings/production.py` sets `SECURE_HSTS_SECONDS = 31536000`. The browser receives duplicate HSTS headers. Decide ownership (Nginx or Django) and remove the redundant one.
- `scripts/renew-ssl-cert.sh` has a hardcoded `SERVER_IP="192.168.0.11"` (~line 26). If the server's LAN IP changes, the renewed cert will carry a stale Subject Alternative Name. Is there a `.env` or CLI argument to override this without editing the script?
- `scripts/renew-ssl-cert.sh` runs monthly via cron and checks expiry 45 days out. It **does** reload Nginx via `systemctl reload nginx` after renewal and logs a warning if the reload fails. Verify the cron entry (`0 3 1 * *`) is installed correctly by `scripts/deploy.sh` and that the log at `/var/log/armguard/ssl-renewal.log` is included in logrotate.
- `scripts/SSL_SELFSIGNED.md` documents the initial cert setup. Verify it is consistent with the current `renew-ssl-cert.sh` parameters (SAN list, validity days, dhparam generation command).

### 16. Error Pages & Information Disclosure
- `templates/404.html` and `templates/500.html` exist and render branded pages with no stack traces, internal paths, Django version, or server headers exposed to the client. Verify both templates load without requiring a logged-in session (unauthenticated 404s must still render correctly).
- `settings/production.py` sets `DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'` (defaults `False`) and emits a `warnings.warn` if `True` is set. This is a soft guard — the server starts anyway. Confirm the deployment runbook or a startup check actively blocks production deployment when `DJANGO_DEBUG=True`.
- Verify `settings/production.py` does not inherit an `INTERNAL_IPS` setting (from a dev import or base.py) that includes the server's LAN address. If `INTERNAL_IPS` contains the server IP, the Django debug toolbar can activate for requests from that IP even with `DEBUG=False`.
- DRF is configured in `settings/production.py` to use `JSONRenderer` only. Verify DRF's default exception handler returns generic messages — not raw Python exception text — on 400/403/404/500 responses.
- The Django admin URL is obscured via `DJANGO_ADMIN_URL` env var (documented in `.env.example` with default `secure-admin`). Confirm the production `.env` overrides this with a unique non-guessable path segment.

---

### Output Format

For each section above:

**Findings**
- `path/to/file.py:line` — description of issue — recommended fix

**Verdict: X/10** — one sentence justification.

---

At the end:

Priority key: 🔴 Critical (fix before next deploy) | 🟠 Medium (fix this sprint) | 🟢 Low (tech debt)

Add one row per finding. Do not limit to 3 rows.

| # | Priority | File | Issue | Fix |
|---|---|---|---|---|

**Refactoring opportunities** (if any — cite specific files)