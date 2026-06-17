from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointmentcapture",
            name="form_snapshot",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Snapshot of the form sections at the time of capture, so data remains readable even if the form is later edited or deleted.",
            ),
        ),
    ]
