from django.urls import path
from .views import (
    PatientRecordSummaryView,
    PatientTimelineView,
    ProviderPatientSummaryView,
    RecordAccessRequestView,
    PatientAccessRequestsView,
    RecordAccessGrantDetailView,
    PatientSensitivityView,
)

urlpatterns = [
    # Patient-facing
    path("patient/<uuid:patient_identity_id>/summary", PatientRecordSummaryView.as_view()),
    path("patient/<uuid:patient_identity_id>/timeline", PatientTimelineView.as_view()),
    path("patient/<uuid:patient_identity_id>/access-requests", PatientAccessRequestsView.as_view()),

    # Provider-facing (consultation panel)
    path("appointment/<str:appointment_id>/patient-summary", ProviderPatientSummaryView.as_view()),

    # Access grant flow
    path("access-request", RecordAccessRequestView.as_view()),
    path("access-grants/<uuid:grant_id>", RecordAccessGrantDetailView.as_view()),

    # Patient sensitivity toggle
    path("sensitivity/<uuid:summary_id>", PatientSensitivityView.as_view()),
]
