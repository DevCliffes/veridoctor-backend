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
record-access action it's attached to. The matching email (if the
recipient has one on file) is sent in a background thread for the same
reason — it must never block or fail the calling view.
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
        notification = Notification.objects.create(
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

    try:
        from identity.emails import send_notification_email_async
        recipient_email = getattr(recipient_identity, "email", None)
        if recipient_email:
            send_notification_email_async(recipient_email, title, message)
    except Exception:
        logger.exception(
            "Failed to dispatch notification email (type=%s, recipient=%s)",
            notification_type,
            getattr(recipient_identity, "id", None),
        )

    return notification


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
# Email is sent automatically as part of notify() above for the patient/
# provider Identity path. The patient_email fallback below additionally
# covers appointments where patient_identity hasn't been linked yet
# (email-matching backfill hasn't run), so the reminder still reaches
# the patient's inbox even without a linked account.
# ─────────────────────────────────────────────────────────────────────────

REMINDER_WINDOWS = {
    "24h": timedelta(hours=24),
    "3h": timedelta(hours=3),
    "10m": timedelta(minutes=10),
}

POLL_TOLERANCE = timedelta(minutes=7)

EXCLUDED_STATUSES = ["cancelled", "completed", "no-show"]


def send_email_reminder(appointment, reminder_type):
    """
    Covers the one case notify() can't handle on its own: a patient with
    no linked Identity yet (patient_identity_id is null), where we still
    have a raw patient_email on the appointment itself. Provider and
    linked-patient emails are already sent via notify() above, so this
    only sends again for patient_email when there's no linked Identity —
    avoiding a duplicate email to the same address.
    """
    if appointment.patient_identity_id:
        return  # already emailed via notify() above

    if not appointment.patient_email:
        return

    from identity.emails import send_notification_email_async

    title, message = _reminder_copy(appointment, reminder_type, for_provider=False)
    send_notification_email_async(appointment.patient_email, title, message)


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
    appointment/reminder_type pair via notify() — which also emails
    them automatically when they have a linked Identity with an email —
    then covers the unlinked-patient email fallback, then logs the send
    so it's never repeated.
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

def build_appointment_email_html(appointment, for_provider, message):
    local_time = timezone.localtime(appointment.start_time).strftime("%a, %d %b · %H:%M")
    appt_type = appointment.appointment_type

    details_html = f"<p><strong>Date &amp; time:</strong> {local_time}</p>"

    if appt_type == "virtual":
        details_html += """
            <p><strong>This is a virtual appointment.</strong></p>
            <ul style="padding-left: 20px; color: #374151;">
                <li>Join at least 5 minutes early.</li>
                <li>Find a quiet, private space with good lighting.</li>
                <li>Check your camera, microphone, and internet connection beforehand.</li>
            </ul>
        """
        meet_id = getattr(appointment, "meet_id", None)
        if meet_id:
            details_html += (
                f'<p><a href="https://veridoctor.com/consult/{meet_id}" '
                f'style="color:#2563EB;">Join video consultation</a></p>'
            )
    else:
        provider = getattr(appointment, "provider", None)
        clinic_name = ""
        address = ""
        county = ""
        country = ""
        if provider is not None:
            clinic_name = provider.clinic_name or ""
            address = provider.address or ""
            county = provider.county or ""
            country = provider.country or ""

        location_line = ", ".join(part for part in [address, county, country] if part)

        details_html += "<p><strong>This is an in-person appointment.</strong></p>"
        if clinic_name:
            details_html += f"<p><strong>Location:</strong> {clinic_name}</p>"
        if location_line:
            details_html += f"<p>{location_line}</p>"
        if not clinic_name and not location_line:
            details_html += "<p>Please contact the clinic for the exact location.</p>"
        details_html += "<p>Please arrive a few minutes early to complete check-in.</p>"

    return f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
            <h2 style="color: #2563EB;">VeriDoctor</h2>
            <p>{message}</p>
            {details_html}
        </div>
    """
