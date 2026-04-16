"""
Migration 0021 — Per-purpose standard loadout quantities.

Adds loadout qty fields for all 6 purposes (holster, mag_pouch, pistol_mag,
pistol_ammo, rifle_sling, rifle_mag, rifle_ammo) so each purpose has its own
configurable auto-fill quantities.

Existing Duty Sentinel fields are kept; the old Duty Security fields (rifle_mag_qty,
rifle_ammo_qty) are kept; new fields are added for both plus Vigil/Guard/Others/OREX.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0020_systemsettings_auto_consumables_accessories'),
    ]

    operations = [
        # ── Duty Sentinel — rifle side ────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Rifle slings auto-issued per Duty Sentinel withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_rifle_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle magazines auto-issued per Duty Sentinel withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_rifle_ammo_qty',
            field=models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Duty Sentinel withdrawal.'),
        ),
        # ── Duty Vigil — all fields ───────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_holster_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Pistol holsters auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_mag_pouch_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Magazine pouches auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_pistol_mag_qty',
            field=models.PositiveSmallIntegerField(default=2, help_text='Pistol magazines auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_pistol_ammo_qty',
            field=models.PositiveSmallIntegerField(default=21, help_text='Pistol ammunition rounds auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Rifle slings auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_rifle_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle magazines auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_rifle_ammo_qty',
            field=models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Duty Vigil withdrawal.'),
        ),
        # ── Duty Security — pistol side + rifle sling ─────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_holster_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Pistol holsters auto-issued per Duty Security withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_mag_pouch_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Magazine pouches auto-issued per Duty Security withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_pistol_mag_qty',
            field=models.PositiveSmallIntegerField(default=2, help_text='Pistol magazines auto-issued per Duty Security withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_pistol_ammo_qty',
            field=models.PositiveSmallIntegerField(default=21, help_text='Pistol ammunition rounds auto-issued per Duty Security withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Rifle slings auto-issued per Duty Security withdrawal.'),
        ),
        # ── Honor Guard — all fields ──────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_holster_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Pistol holsters auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_mag_pouch_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Magazine pouches auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_pistol_mag_qty',
            field=models.PositiveSmallIntegerField(default=2, help_text='Pistol magazines auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_pistol_ammo_qty',
            field=models.PositiveSmallIntegerField(default=21, help_text='Pistol ammunition rounds auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Rifle slings auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_rifle_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle magazines auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_rifle_ammo_qty',
            field=models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Honor Guard withdrawal.'),
        ),
        # ── Others — all fields ───────────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='others_holster_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Pistol holsters auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_mag_pouch_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Magazine pouches auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_pistol_mag_qty',
            field=models.PositiveSmallIntegerField(default=4, help_text='Pistol magazines auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_pistol_ammo_qty',
            field=models.PositiveSmallIntegerField(default=42, help_text='Pistol ammunition rounds auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Rifle slings auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_rifle_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle magazines auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_rifle_ammo_qty',
            field=models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Others withdrawal.'),
        ),
        # ── OREX — all fields ─────────────────────────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='orex_holster_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Pistol holsters auto-issued per OREX withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_mag_pouch_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Magazine pouches auto-issued per OREX withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_pistol_mag_qty',
            field=models.PositiveSmallIntegerField(default=4, help_text='Pistol magazines auto-issued per OREX withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_pistol_ammo_qty',
            field=models.PositiveSmallIntegerField(default=42, help_text='Pistol ammunition rounds auto-issued per OREX withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_rifle_sling_qty',
            field=models.PositiveSmallIntegerField(default=1, help_text='Rifle slings auto-issued per OREX withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_rifle_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle magazines auto-issued per OREX withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_rifle_ammo_qty',
            field=models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per OREX withdrawal.'),
        ),
    ]
