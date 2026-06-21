from django.urls import path
from .views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)

urlpatterns = [
    path("", NotificationListView.as_view()),
    path("mark-all-read/", NotificationMarkAllReadView.as_view()),
    path("<str:notification_id>/read/", NotificationMarkReadView.as_view()),
]
