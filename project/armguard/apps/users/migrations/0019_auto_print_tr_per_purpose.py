"""
Repair migration: adds the six per-purpose auto_print_tr fields to SystemSettings.

Why this exists
---------------
Migration 0018 was originally published with a single ``auto_print_tr``
BooleanField.  It was later rewritten in-place to add the six per-purpose
fields instead.  Any server that had already applied the original 0018 (and
therefore has the old single column but NOT the six new ones) will get a 500
error because the model code references the new columns.

This migration is safe to run in both states:
  - Old 0018 applied  → DB has ``auto_print_tr`` but not the six new columns.
    RunPython adds the six missing columns.  The orphaned ``auto_print_tr``
    column is left in place (SQLite cannot drop columns below v3.35; the model
    no longer references it so Django ignores it at runtime).
  - New 0018 applied  → DB already has the six per-purpose columns.
    RunPython detects this and skips, completing successfully without error.
"""
from django.db import migrations

_NEW_COLS = [
    'auto_print_tr_duty_sentinel',
    'auto_print_tr_duty_vigil',
    'auto_print_tr_duty_security',
    'auto_print_tr_honor_guard',
    'auto_print_tr_others',
    'auto_print_tr_orex',
]


def _add_missing_auto_print_cols(apps, schema_editor):
    """Add the six per-purpose auto-print columns only if they do not exist."""
    conn = schema_editor.connection
    # Use Django's DB-agnostic introspection for all backends.
    # PRAGMA is SQLite-only and must never be sent to PostgreSQL — doing so
    # inside a transaction causes PostgreSQL to abort the entire transaction
    # before the except clause can run.
    if conn.vendor == 'sqlite':
        with conn.cursor() as cur:
            cur.execute("PRAGMA table_info(users_systemsettings)")
            existing = {row[1] for row in cur.fetchall()}
    else:
        with conn.cursor() as cur:
            existing = {
                col.name
                for col in conn.introspection.get_table_description(
                    cur, 'users_systemsettings'
                )
            }

    # PostgreSQL uses 'false' literal; SQLite accepts both 0 and false.
    bool_default = 'false' if conn.vendor == 'postgresql' else '0'
    with conn.cursor() as cur:
        for col in _NEW_COLS:
            if col not in existing:
                cur.execute(
                    f'ALTER TABLE "users_systemsettings" '
                    f'ADD COLUMN "{col}" bool NOT NULL DEFAULT {bool_default}'
                )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0018_systemsettings_auto_print_tr'),
    ]

    operations = [
        migrations.RunPython(
            _add_missing_auto_print_cols,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
