import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0003_providerappointment_service"),
        ("identity", "0007_authcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerappointment",
            name="patient_identity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="patient_appointments",
                to="identity.identity",
            ),
        ),
    ]
