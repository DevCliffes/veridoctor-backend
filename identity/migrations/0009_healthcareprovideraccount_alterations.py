from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0008_patientaccount_fields_fake"),
    ]

    operations = [
        migrations.AlterField(
            model_name="healthcareprovideraccount",
            name="licence_number",
            field=models.CharField(max_length=255, unique=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="healthcareprovideraccount",
            name="licence_type",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="healthcareprovideraccount",
            name="practice_type",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
    ]
