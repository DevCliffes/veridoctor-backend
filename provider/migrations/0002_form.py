from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('provider', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Form',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),
                ('name', models.CharField(max_length=200)),
                ('sections', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provider', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='forms', to='provider.healthcareprovider')),
            ],
        ),
    ]
