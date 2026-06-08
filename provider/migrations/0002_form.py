from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('identity', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='HealthcareProvider',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, serialize=False, editable=False)),
                ('phone_number', models.CharField(blank=True, max_length=20, null=True)),
                ('licence_number', models.CharField(blank=True, max_length=100, null=True)),
                ('licence_type', models.CharField(blank=True, max_length=100, null=True)),
                ('speciality', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('identity', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='provider_profile', to='identity.identity')),
            ],
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, serialize=False, editable=False)),
                ('name', models.CharField(max_length=200)),
                ('estimated_duration', models.IntegerField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='KES', max_length=10)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='services', to='provider.healthcareprovider')),
            ],
        ),
        migrations.CreateModel(
            name='Form',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, serialize=False, editable=False)),
                ('name', models.CharField(max_length=200)),
                ('sections', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forms', to='provider.healthcareprovider')),
            ],
        ),
    ]
