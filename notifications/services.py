"""
Small helper so creating a notification from inside an existing view is a
one-line call rather than repeating Notification.objects.create(...) with
all its fields everywhere. Import this from appointments/views.py,
provider/views.py, records/views.py wherever a notification-worthy event
happens.

Usage:
    from notifications.services import notify

    notify(
        recipient_identity=patient_identity,
        notification_type="appointment_booked",
        title="New appointment request",
        message=f"Dr. {provider_name} has a new appointment with you.",
        link=f"/appointments/{appointment.id}",
    )

Deliberately fails silently (logs, doesn't raise) — a notification that
fails to write should never break the actual appointment/prescription/
record-access action it's attached to.
"""

import logging
from .models import Notification

logger = logging.getLogger(__name__)


def notify(recipient_identity, notification_type, title, message="", link=""):
    if recipient_identity is None:
        return None
    try:
        return Notification.objects.create(
            recipient_identity=recipient_identity,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
        )
    except Exception:
        logger.exception(
            "Failed to create notification (type=%s, recipient=%s)",
            notification_type,
            getattr(recipient_identity, "id", None),
        )
        return None
