import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0015_remove_facility_fields_from_healthcareprovider"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerschedule",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schedules",
                to="provider.providerlocation",
            ),
        ),
    ]
