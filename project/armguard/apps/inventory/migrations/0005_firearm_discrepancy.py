from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inventory',     '0004_pistol_rifle_remarks'),
        ('personnel',     '0001_initial'),
        ('transactions',  '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FirearmDiscrepancy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('firearm_type', models.CharField(
                    choices=[('Pistol', 'Pistol'), ('Rifle', 'Rifle')],
                    max_length=10,
                )),
                ('pistol', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discrepancies',
                    to='inventory.pistol',
                )),
                ('rifle', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discrepancies',
                    to='inventory.rifle',
                )),
                ('issuer', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discrepancies_issued',
                    to='personnel.personnel',
                )),
                ('withdrawer', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discrepancies_withdrawn',
                    to='personnel.personnel',
                )),
                ('related_transaction', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discrepancies',
                    to='transactions.transaction',
                )),
                ('discrepancy_type', models.CharField(
                    choices=[
                        ('Missing',                'Missing'),
                        ('Damaged',                'Damaged'),
                        ('Wrong Serial',           'Wrong Serial'),
                        ('Condition Mismatch',     'Condition Mismatch'),
                        ('Extra Rounds',           'Extra Rounds'),
                        ('Incomplete Accessories', 'Incomplete Accessories'),
                        ('Others',                 'Others'),
                    ],
                    max_length=50,
                )),
                ('description', models.TextField(help_text='Detailed description of the discrepancy.')),
                ('status', models.CharField(
                    choices=[
                        ('Open',         'Open'),
                        ('Under Review', 'Under Review'),
                        ('Resolved',     'Resolved'),
                        ('Closed',       'Closed'),
                    ],
                    default='Open',
                    max_length=20,
                )),
                ('reported_by', models.CharField(
                    help_text='Username of the staff member who reported this discrepancy.',
                    max_length=100,
                )),
                ('reported_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('resolved_by', models.CharField(blank=True, max_length=100, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('resolution_notes', models.TextField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Firearm Discrepancy',
                'verbose_name_plural': 'Firearm Discrepancies',
                'ordering': ['-reported_at'],
            },
        ),
    ]
