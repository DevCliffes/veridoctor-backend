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
from datetime import timedelta

from django.utils import timezone

from .models import Notification, AppointmentReminderLog

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


# ─────────────────────────────────────────────────────────────────────────
# Appointment reminders
#
# Triggered by a periodic poll (a GitHub Actions cron workflow hits
# POST /notifications/send-reminders every 5 minutes). For each of the
# three reminder windows (24h, 3h, 10m before an appointment's start_time),
# finds appointments now due for that specific reminder and not yet sent,
# creates in-app notifications for the patient (when linked) and the
# provider, and logs the send so the next poll never repeats it.
#
# Email is now wired up via Resend — see send_email_reminder() below.
# ─────────────────────────────────────────────────────────────────────────

# How far before the appointment each reminder should fire.
REMINDER_WINDOWS = {
    "24h": timedelta(hours=24),
    "3h": timedelta(hours=3),
    "10m": timedelta(minutes=10),
}

# How wide a window we accept around the exact target time. Must be at
# least as large as the poll interval (5 minutes) so no appointment falls
# through the gap between two consecutive polls. A little extra margin
# absorbs small delays in the cron firing.
POLL_TOLERANCE = timedelta(minutes=7)

# Appointments in these statuses should never receive reminders.
EXCLUDED_STATUSES = ["cancelled", "completed", "no-show"]


def send_email_reminder(appointment, reminder_type):
    """
    Sends the actual reminder email to patient and provider (when an
    email address is available for each), via Resend. Reuses
    _reminder_copy() so wording stays identical to the in-app version.
    """
    from identity.emails import send_appointment_reminder_email

    if appointment.patient_email:
        title, message = _reminder_copy(appointment, reminder_type, for_provider=False)
        send_appointment_reminder_email(appointment.patient_email, title, message)

    try:
        provider_email = appointment.provider.identity.email
    except Exception:
        provider_email = None

    if provider_email:
        title, message = _reminder_copy(appointment, reminder_type, for_provider=True)
        send_appointment_reminder_email(provider_email, title, message)


def _reminder_copy(appointment, reminder_type, for_provider):
    """Returns (title, message) text for a given reminder window and audience."""
    when_label = {
        "24h": "in 24 hours",
        "3h": "in 3 hours",
        "10m": "in 10 minutes",
    }[reminder_type]

    local_time = timezone.localtime(appointment.start_time).strftime("%a, %d %b · %H:%M")
    title = f"Upcoming appointment {when_label}"

    if for_provider:
        patient_name = f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()
        message = f"Your appointment with {patient_name} is at {local_time}."
    else:
        provider_name = "your provider"
        try:
            provider_identity = appointment.provider.identity
            provider_name = f"Dr. {provider_identity.first_name} {provider_identity.last_name}".strip()
        except Exception:
            pass
        message = f"Your appointment with {provider_name} is at {local_time}."

    return title, message


def _send_reminder_for_appointment(appointment, reminder_type):
    """
    Creates the in-app notifications (patient + provider) for one
    appointment/reminder_type pair via notify(), sends the matching
    email reminder, then logs it so it's never repeated. Skips the
    patient in-app notification if there's no linked Identity yet
    (patient_identity is null until the email-matching backfill links
    it) — email still goes out to patient_email regardless, since that
    doesn't depend on a linked Identity.
    """
    link = f"/appointments/{appointment.id}"

    try:
        provider_identity = appointment.provider.identity
    except Exception:
        provider_identity = None

    if provider_identity is not None:
        title, message = _reminder_copy(appointment, reminder_type, for_provider=True)
        notify(
            recipient_identity=provider_identity,
            notification_type="appointment_reminder",
            title=title,
            message=message,
            link=link,
        )

    if appointment.patient_identity_id:
        title, message = _reminder_copy(appointment, reminder_type, for_provider=False)
        notify(
            recipient_identity=appointment.patient_identity,
            notification_type="appointment_reminder",
            title=title,
            message=message,
            link=link,
        )

    send_email_reminder(appointment, reminder_type)

    AppointmentReminderLog.objects.create(
        appointment=appointment,
        reminder_type=reminder_type,
    )


def send_due_reminders():
    """
    Main entry point, called by the reminder endpoint. Checks all three
    reminder windows and sends any that are now due. Returns a small
    summary dict for the endpoint to return as JSON.
    """
    from appointments.models import ProviderAppointment

    now = timezone.now()
    sent_counts = {"24h": 0, "3h": 0, "10m": 0}

    candidates = ProviderAppointment.objects.exclude(
        status__in=EXCLUDED_STATUSES
    ).select_related("provider__identity", "patient_identity")

    for reminder_type, lead_time in REMINDER_WINDOWS.items():
        target_time = now + lead_time
        window_start = target_time - POLL_TOLERANCE
        window_end = target_time + POLL_TOLERANCE

        due = candidates.filter(
            start_time__gte=window_start,
            start_time__lte=window_end,
        ).exclude(
            reminder_logs__reminder_type=reminder_type,
        )

        for appointment in due:
            _send_reminder_for_appointment(appointment, reminder_type)
            sent_counts[reminder_type] += 1

    return sent_counts
