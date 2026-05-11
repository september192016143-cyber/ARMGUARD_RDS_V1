#!/usr/bin/env bash
# =============================================================================
# migrate-to-postgresql.sh — Migrate ArmGuard RDS from SQLite to PostgreSQL
#
# P1-Critical risk mitigation: eliminates SQLite's single-writer concurrency
# limit and the gunicorn workers=1 constraint imposed by scripts/gunicorn.conf.py
#
# Prerequisites on the server:
#   • Python virtual environment activated (source /path/to/venv/bin/activate)
#   • PROJECT_DIR set to the project root (directory containing manage.py)
#   • PostgreSQL 14+ installed (or installed by this script)
#   • Running as a user with sudo privileges
#
# Usage:
#   cd /path/to/armguard          # repo root (contains manage.py in project/)
#   bash scripts/migrate-to-postgresql.sh
#
# After the migration update .env with:
#   DB_ENGINE=django.db.backends.postgresql
#   DB_NAME=armguard
#   DB_USER=armguard
#   DB_PASSWORD=<strong-random-password>
#   DB_HOST=127.0.0.1
#   DB_PORT=5432
# =============================================================================

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(dirname "$0")/../project}"
ENV_FILE="${ENV_FILE:-$(dirname "$0")/../.env}"
DUMP_FILE="/tmp/armguard_datadump_$(date +%Y%m%d_%H%M%S).json"

echo "=== ArmGuard: SQLite → PostgreSQL Migration ==="
echo "Project dir : $PROJECT_DIR"
echo "Env file    : $ENV_FILE"
echo "Data dump   : $DUMP_FILE"
echo

# ---------------------------------------------------------------------------
# 1. Install PostgreSQL (skip if already installed)
# ---------------------------------------------------------------------------
if ! command -v psql &>/dev/null; then
    echo "[1/7] Installing PostgreSQL..."
    sudo apt-get update -qq
    sudo apt-get install -y postgresql postgresql-contrib
else
    echo "[1/7] PostgreSQL already installed — skipping."
fi

# Ensure the service is running
sudo systemctl enable postgresql --quiet
sudo systemctl start postgresql

# ---------------------------------------------------------------------------
# 2. Create the database role and database
# ---------------------------------------------------------------------------
echo
echo "[2/7] Creating PostgreSQL role 'armguard' and database 'armguard'..."

# Prompt for the DB password so it is never stored in this script
read -rsp "Enter a strong password for the 'armguard' PostgreSQL user: " DB_PASS
echo

sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'armguard') THEN
    CREATE ROLE armguard LOGIN PASSWORD '${DB_PASS}';
  ELSE
    ALTER ROLE armguard LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;

SELECT 'Database exists' WHERE EXISTS (SELECT FROM pg_database WHERE datname = 'armguard')
UNION ALL
SELECT 'Creating database' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'armguard');
SQL

sudo -u postgres bash -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='armguard'\" | grep -q 1 || createdb -O armguard armguard"

echo "   Role and database ready."

# ---------------------------------------------------------------------------
# 3. Export the existing SQLite data
# ---------------------------------------------------------------------------
echo
echo "[3/7] Exporting SQLite data to $DUMP_FILE ..."
cd "$PROJECT_DIR"
python manage.py dumpdata \
    --natural-foreign \
    --natural-primary \
    --exclude contenttypes \
    --exclude auth.permission \
    --indent 2 \
    > "$DUMP_FILE"

echo "   Dump complete ($(du -sh "$DUMP_FILE" | cut -f1))."

# ---------------------------------------------------------------------------
# 4. Update .env to use PostgreSQL
# ---------------------------------------------------------------------------
echo
echo "[4/7] Updating .env to use PostgreSQL..."

# Backup original .env
cp "$ENV_FILE" "${ENV_FILE}.sqlite-backup-$(date +%Y%m%d_%H%M%S)"

# Replace or append the DB settings
python3 - <<PYEOF
import re, pathlib

env_path = pathlib.Path('${ENV_FILE}')
text = env_path.read_text()

new_settings = {
    'DB_ENGINE':   'django.db.backends.postgresql',
    'DB_NAME':     'armguard',
    'DB_USER':     'armguard',
    'DB_PASSWORD': '${DB_PASS}',
    'DB_HOST':     '127.0.0.1',
    'DB_PORT':     '5432',
}

for key, val in new_settings.items():
    pattern = rf'^#?\\s*{re.escape(key)}\\s*=.*\$'
    replacement = f'{key}={val}'
    if re.search(pattern, text, re.MULTILINE):
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    else:
        text += f'\\n{key}={val}\\n'

env_path.write_text(text)
print('   .env updated.')
PYEOF

# ---------------------------------------------------------------------------
# 5. Apply Django migrations to the new PostgreSQL database
# ---------------------------------------------------------------------------
echo
echo "[5/7] Running Django migrations against PostgreSQL..."
python manage.py migrate --run-syncdb

# ---------------------------------------------------------------------------
# 6. Load the exported data into PostgreSQL
# ---------------------------------------------------------------------------
echo
echo "[6/7] Loading data into PostgreSQL..."
python manage.py loaddata "$DUMP_FILE"
echo "   Data loaded successfully."

# ---------------------------------------------------------------------------
# 7. Restart Gunicorn
# ---------------------------------------------------------------------------
echo
echo "[7/7] Restarting Gunicorn service..."
if systemctl is-active --quiet armguard-gunicorn 2>/dev/null; then
    sudo systemctl restart armguard-gunicorn
    echo "   Gunicorn restarted."
else
    echo "   (armguard-gunicorn service not active — restart manually after verifying)"
fi

echo
echo "=== Migration complete ==="
echo "SQLite data dump retained at: $DUMP_FILE"
echo ".env backup retained at: ${ENV_FILE}.sqlite-backup-*"
echo
echo "Post-migration checklist:"
echo "  1. Verify the application loads: curl -sk https://localhost/login/"
echo "  2. Confirm workers > 1 in scripts/gunicorn.conf.py (DB_ENGINE is now postgresql)"
echo "  3. Remove or archive the SQLite file: project/db.sqlite3"
echo "  4. Delete the data dump: $DUMP_FILE"
