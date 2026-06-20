from django.db import models
from shared.models import BaseModel


class Notification(BaseModel):
    """
    A single in-app notification for a recipient (provider or patient).

    Created server-side from inside existing views whenever something
    notification-worthy happens (appointment booked/confirmed/cancelled/
    rescheduled, prescription added, record access requested/granted).

    Not a new event system — just a row written alongside whatever the
    triggering view was already doing, so it stays simple and doesn't
    require any new infrastructure (no websockets, no task queue).
    """

    NOTIFICATION_TYPE_CHOICES = [
        ("appointment_booked", "Appointment booked"),
        ("appointment_confirmed", "Appointment confirmed"),
        ("appointment_cancelled", "Appointment cancelled"),
        ("appointment_rescheduled", "Appointment rescheduled"),
        ("prescription_added", "Prescription added"),
        ("record_access_requested", "Record access requested"),
        ("record_access_granted", "Record access granted"),
    ]

    recipient_identity = models.ForeignKey(
        "identity.Identity",
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Who this notification is for — the provider or patient "
                   "that should see it.",
    )
    notification_type = models.CharField(
        max_length=40, choices=NOTIFICATION_TYPE_CHOICES
    )
    title = models.CharField(max_length=255)
    message = models.CharField(max_length=500, blank=True)
    link = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional relative frontend path to navigate to when "
                   "clicked, e.g. '/appointments/<id>'.",
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_identity", "is_read"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} -> {self.recipient_identity_id}"
