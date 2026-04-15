from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0016_systemsettings_idle_timeouts'),
    ]

    operations = [
        # ── TR / PAR defaults ─────────────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='tr_default_return_hours',
            field=models.PositiveSmallIntegerField(
                default=24,
                help_text='Default TR return deadline pre-filled on the New Transaction form (hours from time of issuance).',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='require_par_document',
            field=models.BooleanField(
                default=True,
                help_text='Require upload of a signed PAR document (PDF) when Issuance Type is PAR.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='default_issuance_type',
            field=models.CharField(
                max_length=50,
                default='TR (Temporary Receipt)',
                choices=[
                    ('TR (Temporary Receipt)', 'TR (Temporary Receipt)'),
                    ('PAR (Property Acknowledgement Receipt)', 'PAR (Property Acknowledgement Receipt)'),
                ],
                help_text='Pre-selected Issuance Type when the New Transaction form first loads.',
            ),
        ),
        # ── Per-purpose auto-consumables ──────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_vigil_auto_consumables',
            field=models.BooleanField(
                default=False,
                help_text='Auto-assign magazines & ammunition for Duty Vigil withdrawals.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_honor_guard_auto_consumables',
            field=models.BooleanField(
                default=False,
                help_text='Auto-assign magazines & ammunition for Honor Guard withdrawals.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_others_auto_consumables',
            field=models.BooleanField(
                default=False,
                help_text='Auto-assign magazines & ammunition for Others withdrawals.',
            ),
        ),
        # ── Duty Sentinel standard loadout ────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_holster_qty',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Pistol holsters auto-issued per Duty Sentinel withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_mag_pouch_qty',
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text='Magazine pouches auto-issued per Duty Sentinel withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_pistol_mag_qty',
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text='Pistol magazines auto-issued per Duty Sentinel withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_pistol_ammo_qty',
            field=models.PositiveSmallIntegerField(
                default=42,
                help_text='Pistol ammunition rounds auto-issued per Duty Sentinel withdrawal.',
            ),
        ),
        # ── Duty Security standard loadout ────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_rifle_mag_qty',
            field=models.PositiveSmallIntegerField(
                default=7,
                help_text='Rifle magazines auto-issued per Duty Security withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_rifle_ammo_qty',
            field=models.PositiveSmallIntegerField(
                default=210,
                help_text='Rifle ammunition rounds auto-issued per Duty Security withdrawal.',
            ),
        ),
        # ── Accessory max quantities ──────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='max_pistol_holster_qty',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Maximum pistol holsters issuable in a single withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='max_magazine_pouch_qty',
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text='Maximum magazine pouches issuable in a single withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='max_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Maximum rifle slings issuable in a single withdrawal.',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='max_bandoleer_qty',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Maximum bandoleers issuable in a single withdrawal.',
            ),
        ),
    ]
