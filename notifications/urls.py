from django.urls import path
from .views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    SendAppointmentRemindersView,
)
from .push_views import PushSubscribeView, PushUnsubscribeView

urlpatterns = [
    path("", NotificationListView.as_view()),
    path("mark-all-read/", NotificationMarkAllReadView.as_view()),
    path("send-reminders/", SendAppointmentRemindersView.as_view()),
    path("push-subscribe/", PushSubscribeView.as_view()),
    path("push-unsubscribe/", PushUnsubscribeView.as_view()),
    path("<str:notification_id>/read/", NotificationMarkReadView.as_view()),
]
