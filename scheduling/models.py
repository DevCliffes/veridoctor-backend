from django.db import models


class Schedule(models.Model):
    """
    Model for the schedule of a healthcare provider
    """

    healthcare_provider = models.ForeignKey(
        "identity.HealthcareProviderAccount", on_delete=models.CASCADE
    )
    day_of_week = models.CharField(max_length=20)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=True)
