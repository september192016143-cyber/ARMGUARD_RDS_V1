"""
Drop the legacy PostgreSQL CHECK constraint txn_purpose_valid.

The constraint was applied directly to the DB (outside Django migrations) and
hardcoded only the original 5 purpose values.  Now that purposes are managed
dynamically via the TransactionPurpose table, this constraint incorrectly
blocks any new purpose (e.g. 'Firing') from being saved and must be removed.

The reverse migration is a no-op: re-adding the constraint with a fixed list
would immediately break dynamic purposes again, so we intentionally leave it
dropped on rollback.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0009_seed_default_purposes'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE transactions_transaction
                DROP CONSTRAINT IF EXISTS txn_purpose_valid;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
