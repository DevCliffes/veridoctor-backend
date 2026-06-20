from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from identity.models import Identity
from .models import Notification
from .serializers import NotificationSerializer


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
