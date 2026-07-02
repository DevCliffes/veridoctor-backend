from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import PushSubscription


class PushSubscribeView(APIView):
    def post(self, request):
        identity_id = request.data.get("identity_id")
        subscription = request.data.get("subscription")

        if not identity_id or not subscription:
            return Response(
                {"detail": "identity_id and subscription are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        endpoint = subscription.get("endpoint")
        keys = subscription.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")

        if not endpoint or not p256dh or not auth:
            return Response(
                {"detail": "Malformed subscription payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PushSubscription.objects.update_or_create(
            identity_id=identity_id,
            endpoint=endpoint,
            defaults={
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
            },
        )
        return Response({"subscribed": True}, status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    def post(self, request):
        identity_id = request.data.get("identity_id")
        endpoint = request.data.get("endpoint")

        if not identity_id or not endpoint:
            return Response(
                {"detail": "identity_id and endpoint are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PushSubscription.objects.filter(
            identity_id=identity_id, endpoint=endpoint
        ).delete()
        return Response({"unsubscribed": True}, status=status.HTTP_200_OK)
