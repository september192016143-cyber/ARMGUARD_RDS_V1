from django.db import migrations, models


def seed_groups(apps, schema_editor):
    PersonnelGroup = apps.get_model('personnel', 'PersonnelGroup')
    defaults = ['HAS', '951st', '952nd', '953rd']
    for i, name in enumerate(defaults):
        PersonnelGroup.objects.get_or_create(name=name, defaults={'order': i})


class Migration(migrations.Migration):

    dependencies = [
        ('personnel', '0003_g8_db_constraints'),
    ]

    operations = [
        migrations.CreateModel(
            name='PersonnelGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Personnel Group',
                'verbose_name_plural': 'Personnel Groups',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.AlterField(
            model_name='personnel',
            name='group',
            field=models.CharField(
                max_length=50,
                choices=[('HAS', 'HAS'), ('951st', '951st'), ('952nd', '952nd'), ('953rd', '953rd')],
            ),
        ),
        migrations.RunPython(seed_groups, migrations.RunPython.noop),
    ]
