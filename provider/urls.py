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
from appointments.views import ProviderAppointmentView, ProviderAppointmentDetailView

urlpatterns = [
    path("<str:identity_id>/services", ServiceView.as_view()),
    path("<str:identity_id>/services/<str:service_id>", ServiceDetailView.as_view()),
    path("<str:identity_id>/forms", FormView.as_view()),
    path("<str:identity_id>/forms/<str:form_id>", FormDetailView.as_view()),
    path("<str:identity_id>/appointments", ProviderAppointmentView.as_view()),
    path("<str:identity_id>/appointments/<str:appointment_id>", ProviderAppointmentDetailView.as_view()),
    path("<str:identity_id>/prescriptions", PrescriptionView.as_view()),
    path("<str:identity_id>/prescriptions/<str:prescription_id>", PrescriptionDetailView.as_view()),

    # Patient-facing — GET /provider/prescriptions?patient_email=xxx
    path("prescriptions", PatientPrescriptionView.as_view()),
]
