from django.urls import path
from .views import (
    ProviderProfileView,
    ServiceView,
    ServiceDetailView,
    FormView,
    FormDetailView,
    PrescriptionView,
    PrescriptionDetailView,
    PatientPrescriptionView,
    ProviderScheduleView,
    ProviderScheduleDetailView,
    ProviderListView,
    ProviderAvailableSlotsView,
    ProviderPublicProfileView,
    PatientDetailView,
    ProviderPhotoUploadView,
)
from appointments.views import (
    ProviderAppointmentView,
    ProviderAppointmentDetailView,
    AppointmentCaptureView,
    ProviderDashboardStatsView,
)

urlpatterns = [
    # Provider directory (no identity_id)
    path("list", ProviderListView.as_view()),
    path("prescriptions", PatientPrescriptionView.as_view()),
    # Profile
    path("<str:identity_id>/profile", ProviderProfileView.as_view()),
    # Profile photo upload
    path("<str:identity_id>/photo", ProviderPhotoUploadView.as_view()),
    # Public profile (patient-facing, used by health portal detail page)
    path("<str:identity_id>/public-profile", ProviderPublicProfileView.as_view()),
    # Available slots
    path("<str:identity_id>/available-slots", ProviderAvailableSlotsView.as_view()),
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
    # Schedule
    path("<str:identity_id>/schedule", ProviderScheduleView.as_view()),
    path("<str:identity_id>/schedule/<str:schedule_id>", ProviderScheduleDetailView.as_view()),
    # Prescriptions
    path("<str:identity_id>/prescriptions", PrescriptionView.as_view()),
    path("<str:identity_id>/prescriptions/<str:prescription_id>", PrescriptionDetailView.as_view()),
    # Patient profile lookup (used by capture page to resolve phone number)
    path("<str:identity_id>/patients/<str:patient_identity_id>", PatientDetailView.as_view()),
]
