from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_seed_magazine_pools'),
    ]

    operations = [
        # Pistol
        migrations.AddField(
            model_name='pistol',
            name='remarks',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pistol',
            name='remarks_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pistol',
            name='remarks_updated_by',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        # Rifle
        migrations.AddField(
            model_name='rifle',
            name='remarks',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rifle',
            name='remarks_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rifle',
            name='remarks_updated_by',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
