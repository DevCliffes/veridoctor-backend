from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0009_healthcareprovideraccount_alterations"),
    ]

    operations = [
        migrations.AddField(
            model_name="healthcareprovideraccount",
            name="subspecialties",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of subspecialty strings e.g. ['Pediatric Cardiology', 'Sports Medicine']",
            ),
        ),
    ]
