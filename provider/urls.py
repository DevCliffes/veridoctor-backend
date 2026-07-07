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
    ProviderDocumentUploadView,
    ProviderGenericImageUploadView,
    ProviderReviewListView,
)
from appointments.views import (
    ProviderAppointmentView,
    ProviderAppointmentDetailView,
    AppointmentCaptureView,
    ProviderDashboardStatsView,
)

urlpatterns = [
    # No identity_id
    path("list", ProviderListView.as_view()),
    path("prescriptions", PatientPrescriptionView.as_view()),

    # Profile
    path("<str:identity_id>/profile", ProviderProfileView.as_view()),
    path("<str:identity_id>/public-profile", ProviderPublicProfileView.as_view()),

    # Photo & document uploads
    path("<str:identity_id>/photo", ProviderPhotoUploadView.as_view()),
    path("<str:identity_id>/document", ProviderDocumentUploadView.as_view()),
    path("<str:identity_id>/upload-image", ProviderGenericImageUploadView.as_view()),

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
    path("<str:identity_id>/appointments/<str:appointment_id>/captures", AppointmentCaptureView.as_view()),

    # Dashboard
    path("<str:identity_id>/dashboard/stats", ProviderDashboardStatsView.as_view()),

    # Schedule
    path("<str:identity_id>/schedule", ProviderScheduleView.as_view()),
    path("<str:identity_id>/schedule/<str:schedule_id>", ProviderScheduleDetailView.as_view()),

    # Prescriptions
    path("<str:identity_id>/prescriptions", PrescriptionView.as_view()),
    path("<str:identity_id>/prescriptions/<str:prescription_id>", PrescriptionDetailView.as_view()),

    # Patient lookup
    path("<str:identity_id>/patients/<str:patient_identity_id>", PatientDetailView.as_view()),

    path("<str:identity_id>/reviews", ProviderReviewListView.as_view()),
]
