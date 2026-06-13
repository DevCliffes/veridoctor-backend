from django.urls import path
from .views import (
    ServiceView,
    ServiceDetailView,
    FormView,
    FormDetailView,
    PrescriptionView,
    PrescriptionDetailView,
    PatientPrescriptionView,
)
from appointments.views import (
    ProviderAppointmentView,
    ProviderAppointmentDetailView,
    AppointmentCaptureView,
    ProviderDashboardStatsView,
)

urlpatterns = [
    # Services
    path("<str:identity_id>/services", ServiceView.as_view()),
    path("<str:identity_id>/services/<str:service_id>", ServiceDetailView.as_view()),

    # Forms
    path("<str:identity_id>/forms", FormView.as_view()),
    path("<str:identity_id>/forms/<str:form_id>", FormDetailView.as_view()),

    # Appointments
    path("<str:identity_id>/appointments", ProviderAppointmentView.as_view()),
    path("<str:identity_id>/appointments/<str:appointment_id>", ProviderAppointmentDetailView.as_view()),

    # Appointment captures
    path("<str:identity_id>/appointments/<str:appointment_id>/captures", AppointmentCaptureView.as_view()),

    # Dashboard stats
    path("<str:identity_id>/dashboard/stats", ProviderDashboardStatsView.as_view()),

    # Prescriptions
    path("<str:identity_id>/prescriptions", PrescriptionView.as_view()),
    path("<str:identity_id>/prescriptions/<str:prescription_id>", PrescriptionDetailView.as_view()),

    # Patient-facing
    path("prescriptions", PatientPrescriptionView.as_view()),
]
