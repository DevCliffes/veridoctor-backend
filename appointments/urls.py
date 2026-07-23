from django.urls import path
from .views import (
    PatientAppointmentView,
    ProviderAppointmentView,
    ProviderAppointmentDetailView,
    AppointmentCaptureView,
    ProviderIncompleteNotesView,
    ProviderMessagedAppointmentsView,
    ProviderMonthlyTrendView,
    ProviderAppointmentTrendView,
)

urlpatterns = [
    path("", PatientAppointmentView.as_view()),
    path("<uuid:appointment_id>/", PatientAppointmentView.as_view()),
    path("provider/<uuid:identity_id>/appointments/", ProviderAppointmentView.as_view()),
    path("provider/<uuid:identity_id>/appointments/<uuid:appointment_id>/", ProviderAppointmentDetailView.as_view()),
    path("provider/<uuid:identity_id>/appointments/<uuid:appointment_id>/captures/", AppointmentCaptureView.as_view()),
    path("provider/<uuid:identity_id>/appointments/incomplete-notes/", ProviderIncompleteNotesView.as_view()),
    path("provider/<uuid:identity_id>/appointments/with-messages/", ProviderMessagedAppointmentsView.as_view()),
    path("provider/<uuid:identity_id>/appointments/monthly-trend/", ProviderMonthlyTrendView.as_view()),
    path("provider/<uuid:identity_id>/appointments/trend/", ProviderAppointmentTrendView.as_view()),
]
