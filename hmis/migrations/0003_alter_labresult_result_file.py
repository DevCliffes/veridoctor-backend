from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hmis", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="labresult",
            name="result_file",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
