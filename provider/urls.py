from django.urls import path
from .views import ServiceView, ServiceDetailView

urlpatterns = [
    path("<str:identity_id>/services", ServiceView.as_view()),
    path("<str:identity_id>/services/<str:service_id>", ServiceDetailView.as_view()),
]
