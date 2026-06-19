import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0001_initial'),
        ('appointments', '0004_providerappointment_patient_identity'),
        ('provider', '0007_prescription_patient_identity'),
        ('identity', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecordAccessGrant',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('requested_category', models.CharField(help_text="Speciality/category of records requested e.g. 'Cardiology'", max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending — awaiting patient response'), ('approved', 'Approved by patient'), ('denied', 'Denied by patient')], default='pending', max_length=20)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('appointment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_grants', to='appointments.providerappointment')),
                ('patient_identity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_grants', to='identity.identity')),
                ('requesting_provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_requests', to='provider.healthcareprovider')),
            ],
            options={
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
        migrations.AlterUniqueTogether(
            name='recordaccessgrant',
            unique_together={('patient_identity', 'requesting_provider', 'appointment', 'requested_category')},
        ),
    ]
