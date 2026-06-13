from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('provider', '0001_initial'),
    ]

    operations = [
        # Add price_visible to Service
        migrations.AddField(
            model_name='service',
            name='price_visible',
            field=models.BooleanField(
                default=True,
                help_text='Whether the price is shown publicly to patients when booking',
            ),
        ),

        # Create Prescription (may already exist in DB — use --fake if needed)
        migrations.CreateModel(
            name='Prescription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('patient_id', models.CharField(blank=True, max_length=255)),
                ('patient_name', models.CharField(blank=True, max_length=255, null=True)),
                ('patient_email', models.EmailField(blank=True, db_index=True, null=True)),
                ('diagnosis', models.TextField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provider', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='prescriptions',
                    to='provider.healthcareprovider',
                )),
            ],
        ),

        # Create PrescriptionDrug
        migrations.CreateModel(
            name='PrescriptionDrug',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('drug_name', models.CharField(max_length=255)),
                ('dosage', models.CharField(blank=True, max_length=100, null=True)),
                ('frequency', models.CharField(max_length=100)),
                ('duration', models.CharField(max_length=100)),
                ('instructions', models.TextField(blank=True, null=True)),
                ('prescription', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='drugs',
                    to='provider.prescription',
                )),
            ],
        ),
    ]
