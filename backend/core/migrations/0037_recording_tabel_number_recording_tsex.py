from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_recording_duration_fixed_recording_duration_ms'),
    ]

    operations = [
        migrations.AddField(
            model_name='recording',
            name='tabel_number',
            field=models.CharField(blank=True, db_index=True, max_length=50, verbose_name='Tabel raqami'),
        ),
        migrations.AddField(
            model_name='recording',
            name='tsex',
            field=models.CharField(blank=True, db_index=True, max_length=200, verbose_name='Sex/tsex'),
        ),
    ]
