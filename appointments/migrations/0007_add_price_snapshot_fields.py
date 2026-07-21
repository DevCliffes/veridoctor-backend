from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0006_provideraappointment_actual_times"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerappointment",
            name="price_at_booking",
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="providerappointment",
            name="currency_at_booking",
            field=models.CharField(max_length=10, null=True, blank=True),
        ),
    ]
