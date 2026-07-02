import json
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from pywebpush import webpush, WebPushException

from .models import Notification, PushSubscription

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def send_push_on_notification_created(sender, instance, created, **kwargs):
    if not created:
        return

    subscriptions = PushSubscription.objects.filter(
        identity_id=instance.recipient_identity_id
    )
    if not subscriptions.exists():
        return

    payload = json.dumps(
        {
            "title": instance.title,
            "body": instance.message,
            "link": instance.link or "/",
            "notification_id": str(instance.id),
        }
    )

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            )
        except WebPushException as e:
            status_code = getattr(e.response, "status_code", None)
            if status_code in (404, 410):
                sub.delete()
            else:
                logger.warning(
                    "Push notification failed for subscription %s: %s", sub.id, e
                )
