from django.urls import path
from .views import ServiceView, ServiceDetailView, FormView, FormDetailView

urlpatterns = [
    path("<str:identity_id>/services", ServiceView.as_view()),
    path("<str:identity_id>/services/<str:service_id>", ServiceDetailView.as_view()),
    path("<str:identity_id>/forms", FormView.as_view()),
    path("<str:identity_id>/forms/<str:form_id>", FormDetailView.as_view()),
]
