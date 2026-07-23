from django.urls import path
from .views import (
    PatientAppointmentView,
    ProviderAppointmentView,
    ProviderAppointmentDetailView,
    AppointmentCaptureView,
    ProviderIncompleteNotesView,
    ProviderMessagedAppointmentsView,
)

urlpatterns = [
    # Patient-facing — list + create
    path("", PatientAppointmentView.as_view()),
    # Patient-facing — update (cancel / reschedule)  ← THIS WAS MISSING
    path("<uuid:appointment_id>/", PatientAppointmentView.as_view()),
    # Provider-facing — list + create
    path("provider/<uuid:identity_id>/appointments/", ProviderAppointmentView.as_view()),
    # Provider-facing — detail, update, delete
    path("provider/<uuid:identity_id>/appointments/<uuid:appointment_id>/", ProviderAppointmentDetailView.as_view()),
    # Appointment captures — list + create
    path("provider/<uuid:identity_id>/appointments/<uuid:appointment_id>/captures/", AppointmentCaptureView.as_view()),
    # Pending-actions panel — appointments concluded with no capture submitted
    path("provider/<uuid:identity_id>/appointments/incomplete-notes/", ProviderIncompleteNotesView.as_view()),
    # Pending-actions panel — upcoming appointments carrying a booking message
    path("provider/<uuid:identity_id>/appointments/with-messages/", ProviderMessagedAppointmentsView.as_view()),
]
