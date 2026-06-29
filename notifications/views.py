import os

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from identity.models import Identity
from .models import Notification
from .serializers import NotificationSerializer
from .services import send_due_reminders


class NotificationListView(APIView):
    """
    GET /notifications?identity_id=<id>
    Returns the most recent 50 notifications for that identity, newest
    first, plus an unread_count so the frontend bell badge doesn't need
    a second request.
    """

    def get(self, request):
        identity_id = request.query_params.get("identity_id")
        if not identity_id:
            return Response(
                {"error": "identity_id query param required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            identity = Identity.objects.get(id=identity_id)
        except Identity.DoesNotExist:
            return Response(
                {"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND
            )
        notifications = Notification.objects.filter(
            recipient_identity=identity
        )[:50]
        unread_count = Notification.objects.filter(
            recipient_identity=identity, is_read=False
        ).count()
        serializer = NotificationSerializer(notifications, many=True)
        return Response(
            {
                "results": serializer.data,
                "unread_count": unread_count,
            }
        )


class NotificationMarkReadView(APIView):
    """
    PATCH /notifications/<notification_id>/read
    Marks a single notification as read.
    """

    def patch(self, request, notification_id):
        try:
            notification = Notification.objects.get(id=notification_id)
        except Notification.DoesNotExist:
            return Response(
                {"error": "Notification not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    """
    POST /notifications/mark-all-read
    Body: { "identity_id": "<id>" }
    Marks every unread notification for that identity as read in one call.
    """

    def post(self, request):
        identity_id = request.data.get("identity_id")
        if not identity_id:
            return Response(
                {"error": "identity_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = Notification.objects.filter(
            recipient_identity_id=identity_id, is_read=False
        ).update(is_read=True)
        return Response({"success": True, "updated": updated})


class SendAppointmentRemindersView(APIView):
    """
    POST /notifications/send-reminders
    Header: X-Reminder-Secret: <shared secret>

    Intended to be called every 5 minutes by a scheduled GitHub Actions
    workflow (not by the frontend, and not by browsers — there's no
    session auth here, only the shared-secret header). Checks all
    appointments for the three reminder windows (24h, 3h, 10m before
    start_time) and sends any that are now due, skipping ones already
    sent. Safe to call repeatedly — sending is deduplicated via
    AppointmentReminderLog.
    """

    def post(self, request):
        expected_secret = os.environ.get("REMINDER_CRON_SECRET")
        provided_secret = request.headers.get("X-Reminder-Secret")

        if not expected_secret:
            # Misconfiguration on our side — fail closed rather than
            # silently accepting every request.
            return Response(
                {"error": "Reminder secret not configured on server"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not provided_secret or provided_secret != expected_secret:
            return Response(
                {"error": "Invalid or missing reminder secret"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        sent_counts = send_due_reminders()
        return Response({"success": True, "sent": sent_counts})
