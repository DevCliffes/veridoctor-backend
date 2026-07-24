from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0008_backfill_price_snapshot"),
        # ProviderLocation itself was created well before this; pegging to
        # 0017 (the latest provider migration in this thread) just
        # guarantees the table already exists by the time this FK is added.
        ("provider", "0017_backfill_providerschedule_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerappointment",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="appointments",
                to="provider.providerlocation",
            ),
        ),
    ]
