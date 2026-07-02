from django.db import models
from shared.models import BaseModel


class Notification(BaseModel):
    """
    A single in-app notification for a recipient (provider or patient).
    """
    NOTIFICATION_TYPE_CHOICES = [
        ("appointment_booked", "Appointment booked"),
        ("appointment_confirmed", "Appointment confirmed"),
        ("appointment_cancelled", "Appointment cancelled"),
        ("appointment_rescheduled", "Appointment rescheduled"),
        ("appointment_reminder", "Appointment reminder"),
        ("prescription_added", "Prescription added"),
        ("prescription_ready", "Prescription ready"),
        ("record_access_requested", "Record access requested"),
        ("record_access_granted", "Record access granted"),
    ]
    recipient_identity = models.ForeignKey(
        "identity.Identity",
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Who this notification is for — the provider or patient that should see it.",
    )
    notification_type = models.CharField(
        max_length=40, choices=NOTIFICATION_TYPE_CHOICES
    )
    title = models.CharField(max_length=255)
    message = models.CharField(max_length=500, blank=True)
    link = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional relative frontend path to navigate to when clicked, e.g. '/appointments/<id>'.",
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_identity", "is_read"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} -> {self.recipient_identity_id}"


class AppointmentReminderLog(BaseModel):
    """
    Tracks which reminder windows have already been sent for a given
    appointment, so the periodic reminder job (polled every 5 minutes by
    a GitHub Actions cron) never sends the same reminder twice.
    One row per (appointment, reminder_type) pair — created the moment
    that specific reminder is sent.
    """
    REMINDER_TYPE_CHOICES = [
        ("24h", "24 hours before"),
        ("3h", "3 hours before"),
        ("10m", "10 minutes before"),
    ]
    appointment = models.ForeignKey(
        "appointments.ProviderAppointment",
        on_delete=models.CASCADE,
        related_name="reminder_logs",
    )
    reminder_type = models.CharField(max_length=10, choices=REMINDER_TYPE_CHOICES)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "reminder_type"],
                name="unique_reminder_per_appointment_and_type",
            )
        ]

    def __str__(self):
        return f"{self.reminder_type} reminder for appointment {self.appointment_id}"


class PushSubscription(BaseModel):
    """
    A single browser/device subscription for Web Push. One identity can
    have multiple rows here (e.g. logged in on phone + laptop).
    """
    identity = models.ForeignKey(
        "identity.Identity",
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["identity", "endpoint"],
                name="unique_push_subscription_per_identity_endpoint",
            )
        ]

    def __str__(self):
        return f"Push subscription for {self.identity_id}"
