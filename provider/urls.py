from django.urls import path
from .views import ServiceView

urlpatterns = [
    path("<str:provider_id>/services", ServiceView.as_view()),
]
