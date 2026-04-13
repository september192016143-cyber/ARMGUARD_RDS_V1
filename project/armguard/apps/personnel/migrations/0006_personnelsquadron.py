"""
0006_personnelsquadron

Creates the PersonnelSquadron model, which is the DB-backed list of
squadrons manageable from the Settings page (mirrors PersonnelGroup).

No changes are made to the Personnel.squadron CharField — it continues
to store a plain string value; the ChoiceField on the form is now
populated from this table instead of being a free-text input.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personnel', '0005_remove_group_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='PersonnelSquadron',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('name', models.CharField(max_length=50, unique=True)),
                ('order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Personnel Squadron',
                'verbose_name_plural': 'Personnel Squadrons',
                'ordering': ['order', 'name'],
            },
        ),
    ]
