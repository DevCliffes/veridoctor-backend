import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0006_fix_never_ending_schedules"),
        ("identity", "0007_authcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="prescription",
            name="patient_identity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prescriptions_received",
                to="identity.identity",
            ),
        ),
    ]
