from django.urls import path
from .views import (
    PatientAppointmentView,
    ProviderAppointmentView,
    ProviderAppointmentDetailView,
    AppointmentCaptureView,
)

urlpatterns = [
    # Patient-facing
    path("", PatientAppointmentView.as_view()),

    # Provider-facing — list + create
    path("provider/<uuid:identity_id>/appointments/", ProviderAppointmentView.as_view()),

    # Provider-facing — detail, update, delete
    path("provider/<uuid:identity_id>/appointments/<uuid:appointment_id>/", ProviderAppointmentDetailView.as_view()),

    # Appointment captures — list + create
    path("provider/<uuid:identity_id>/appointments/<uuid:appointment_id>/captures/", AppointmentCaptureView.as_view()),
]
