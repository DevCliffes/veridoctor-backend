import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0002_appointmentcapture_form_snapshot"),
        ("provider", "0005_sync_provider_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerappointment",
            name="service",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="appointments",
                to="provider.service",
            ),
        ),
    ]
