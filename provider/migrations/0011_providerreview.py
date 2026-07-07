import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0010_healthcareprovider_profile_complete"),
        ("appointments", "0006_provideraappointment_actual_times"),
        ("identity", "0001_initial"),  # adjust if your identity app's latest/initial migration has a different name
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("patient_first_name", models.CharField(max_length=255)),
                ("patient_last_name", models.CharField(blank=True, max_length=255)),
                ("rating", models.PositiveSmallIntegerField()),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("appointment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="review", to="appointments.providerappointment")),
                ("patient_identity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="provider_reviews", to="identity.identity")),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="provider.healthcareprovider")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
