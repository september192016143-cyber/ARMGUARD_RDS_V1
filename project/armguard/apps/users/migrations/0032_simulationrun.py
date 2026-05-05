"""
Migration 0032: Add SimulationRun model.

SimulationRun tracks OREX withdrawal simulations that run in a background
thread.  The web view creates the record and starts the thread immediately,
returning a redirect to the dashboard.  The thread writes progress and final
results back to this table as it runs.
"""
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0031_systemlog'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SimulationRun',
            fields=[
                ('run_id', models.UUIDField(
                    primary_key=True,
                    default=uuid.uuid4,
                    editable=False,
                    serialize=False,
                )),
                ('status', models.CharField(
                    max_length=20,
                    choices=[
                        ('queued',    'Queued'),
                        ('running',   'Running'),
                        ('completed', 'Completed'),
                        ('error',     'Error'),
                    ],
                    default='queued',
                    db_index=True,
                )),
                ('operator',      models.CharField(max_length=150)),
                ('commit',        models.BooleanField(default=False)),
                ('sim_count',     models.PositiveIntegerField(default=114)),
                ('delay_seconds', models.PositiveIntegerField(default=5)),
                ('ok_count',      models.IntegerField(default=0)),
                ('err_count',     models.IntegerField(default=0)),
                ('skip_count',    models.IntegerField(default=0)),
                ('total',         models.IntegerField(default=0)),
                ('progress',      models.IntegerField(default=0)),
                ('wall_time',     models.FloatField(null=True, blank=True)),
                ('results_json',  models.JSONField(default=list, blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('started_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='simulation_runs',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('started_at',   models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(null=True, blank=True)),
            ],
            options={
                'verbose_name':        'Simulation Run',
                'verbose_name_plural': 'Simulation Runs',
                'ordering':            ['-started_at'],
            },
        ),
    ]
