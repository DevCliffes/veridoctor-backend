from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0013_backfill_providerlocation_data"),
    ]

    operations = [
        migrations.RemoveField(model_name="healthcareprovider", name="clinic_name"),
        migrations.RemoveField(model_name="healthcareprovider", name="address"),
        migrations.RemoveField(model_name="healthcareprovider", name="county"),
        migrations.RemoveField(model_name="healthcareprovider", name="country"),
        migrations.RemoveField(model_name="healthcareprovider", name="clinic_logo_url"),
        migrations.RemoveField(model_name="healthcareprovider", name="business_reg_number"),
        migrations.RemoveField(model_name="healthcareprovider", name="business_reg_image"),
        migrations.RemoveField(model_name="healthcareprovider", name="operating_licence"),
        migrations.RemoveField(model_name="healthcareprovider", name="operating_licence_image"),
        migrations.RemoveField(model_name="healthcareprovider", name="kra_pin"),
        migrations.RemoveField(model_name="healthcareprovider", name="kra_pin_image"),
        migrations.RemoveField(model_name="healthcareprovider", name="cr12_image"),
        migrations.AlterField(
            model_name="providerdocumentreview",
            name="field_name",
            field=models.CharField(
                choices=[
                    ("national_id_image", "National ID"),
                    ("valid_licence_image", "Valid Licence"),
                ],
                max_length=64,
            ),
        ),
    ]
