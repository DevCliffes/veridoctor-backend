from django.urls import path
from .views import ServiceView

urlpatterns = [
    path("<str:identity_id>/services", ServiceView.as_view()),
]
