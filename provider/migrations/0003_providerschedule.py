import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('provider', '0002_service_price_visible'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProviderSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('location_type', models.CharField(choices=[('virtual', 'virtual'), ('physical', 'physical'), ('both', 'both')], default='virtual', max_length=10)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('recurrence', models.CharField(choices=[('none', 'none'), ('daily', 'daily'), ('weekdays', 'weekdays'), ('weekly', 'weekly'), ('custom', 'custom')], default='none', max_length=10)),
                ('recurrence_interval', models.PositiveIntegerField(default=1)),
                ('recurrence_days', models.JSONField(blank=True, default=list)),
                ('recurrence_end_type', models.CharField(blank=True, choices=[('never', 'never'), ('on_date', 'on_date'), ('after', 'after')], max_length=10, null=True)),
                ('recurrence_end_date', models.DateField(blank=True, null=True)),
                ('recurrence_count', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='provider.healthcareprovider')),
                ('service', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedules', to='provider.service')),
            ],
        ),
    ]
