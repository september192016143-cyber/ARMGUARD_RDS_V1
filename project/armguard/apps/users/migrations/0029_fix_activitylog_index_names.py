"""
Migration 0029: Stabilise ActivityLog index names and sync field help_text.

WHY THIS EXISTS
---------------
Migrations 0027/0028 created indexes with custom names (actlog_user_ts_idx etc.)
but the model's Meta.indexes had no explicit name= — so Django kept auto-generating
a rename migration on every deployment (server-generated, not in repo).

This migration:
  1. Renames the 4 custom index names to Django's auto-generated equivalents using
     conditional SQL (DO $$ IF EXISTS ... $$) so it is safe whether the indexes
     have already been renamed (server had an applied-and-deleted rename migration)
     or still carry the old custom names (fresh install).
  2. Syncs help_text on 7 fields so the migration state matches the model exactly,
     preventing AlterField auto-generation on future deployments.

After this migration, the model's explicit name= values match the migration state,
so makemigrations will generate no further index-related migrations.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0028_activitylog_flag_exception_search'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── 1. Rename indexes ─────────────────────────────────────────────────
        # state_operations: update Django's migration graph (no DB touch)
        # database_operations: conditional SQL — skips silently if already renamed
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameIndex(
                    'activitylog',
                    old_name='actlog_user_ts_idx',
                    new_name='users_activ_user_id_8a5363_idx',
                ),
                migrations.RenameIndex(
                    'activitylog',
                    old_name='actlog_path_ts_idx',
                    new_name='users_activ_path_873007_idx',
                ),
                migrations.RenameIndex(
                    'activitylog',
                    old_name='actlog_status_ts_idx',
                    new_name='users_activ_status__cc100a_idx',
                ),
                migrations.RenameIndex(
                    'activitylog',
                    old_name='actlog_flag_ts_idx',
                    new_name='users_activ_flag_04e3b5_idx',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DO $$ BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_indexes WHERE indexname = 'actlog_user_ts_idx'
                        ) THEN
                            ALTER INDEX actlog_user_ts_idx
                                RENAME TO users_activ_user_id_8a5363_idx;
                        END IF;

                        IF EXISTS (
                            SELECT 1 FROM pg_indexes WHERE indexname = 'actlog_path_ts_idx'
                        ) THEN
                            ALTER INDEX actlog_path_ts_idx
                                RENAME TO users_activ_path_873007_idx;
                        END IF;

                        IF EXISTS (
                            SELECT 1 FROM pg_indexes WHERE indexname = 'actlog_status_ts_idx'
                        ) THEN
                            ALTER INDEX actlog_status_ts_idx
                                RENAME TO users_activ_status__cc100a_idx;
                        END IF;

                        IF EXISTS (
                            SELECT 1 FROM pg_indexes WHERE indexname = 'actlog_flag_ts_idx'
                        ) THEN
                            ALTER INDEX actlog_flag_ts_idx
                                RENAME TO users_activ_flag_04e3b5_idx;
                        END IF;
                    END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),

        # ── 2. Sync help_text in migration state to match current model ───────
        # These are metadata-only changes — no SQL is emitted against the DB.
        # They exist solely to stop makemigrations from regenerating AlterField
        # operations on every server deployment.
        migrations.AlterField(
            model_name='activitylog',
            name='session_key',
            field=models.CharField(
                blank=True, max_length=40,
                help_text='Django session key (links anonymous requests across a session).',
            ),
        ),
        migrations.AlterField(
            model_name='activitylog',
            name='path',
            field=models.CharField(
                max_length=2048,
                help_text='Request path (URL without scheme/host).',
            ),
        ),
        migrations.AlterField(
            model_name='activitylog',
            name='query_string',
            field=models.TextField(
                blank=True,
                help_text="Raw query string (e.g. 'q=pistol&status=Active').",
            ),
        ),
        migrations.AlterField(
            model_name='activitylog',
            name='view_name',
            field=models.CharField(
                blank=True, max_length=255,
                help_text="Resolved Django URL name (e.g. 'transactions:create').",
            ),
        ),
        migrations.AlterField(
            model_name='activitylog',
            name='referer',
            field=models.CharField(
                blank=True, max_length=2048,
                help_text='HTTP Referer header \u2014 the page the user came from.',
            ),
        ),
        migrations.AlterField(
            model_name='activitylog',
            name='user',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='activity_logs',
                to=settings.AUTH_USER_MODEL,
                help_text='Authenticated user; null for anonymous requests.',
            ),
        ),
        migrations.AlterField(
            model_name='activitylog',
            name='search_query',
            field=models.CharField(
                blank=True, max_length=500, db_index=True,
                help_text='Value of ?q=, ?search=, or ?query= param \u2014 empty if not a search request.',
            ),
        ),
    ]
