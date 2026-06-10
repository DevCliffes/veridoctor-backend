from django.urls import path
from .views import PatientAppointmentView

urlpatterns = [
    path("", PatientAppointmentView.as_view()),
]
