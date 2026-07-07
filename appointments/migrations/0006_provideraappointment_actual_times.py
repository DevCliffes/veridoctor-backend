from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0005_alter_appointmentcapture_form_snapshot_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="provideraappointment",
            name="actual_start_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="provideraappointment",
            name="actual_end_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
