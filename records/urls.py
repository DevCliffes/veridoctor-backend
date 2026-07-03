from django.urls import path
from .views import (
    PatientRecordSummaryView,
    PatientTimelineView,
    ProviderPatientTimelineView,
    ProviderPatientSummaryView,
    RecordAccessRequestView,
    PatientAccessRequestsView,
    RecordAccessGrantDetailView,
    PatientSensitivityView,
)
from .pin_views import (
    RecordsPinStatusView,
    RecordsPinSetView,
    RecordsPinVerifyView,
    RecordsPinChangeView,
    RecordsPinResetView,
)

urlpatterns = [
    # Patient-facing
    path("patient/<uuid:patient_identity_id>/summary", PatientRecordSummaryView.as_view()),
    path("patient/<uuid:patient_identity_id>/timeline", PatientTimelineView.as_view()),
    path("patient/<uuid:patient_identity_id>/access-requests", PatientAccessRequestsView.as_view()),

    # Provider-facing (own records for a patient — no PIN, relationship-gated instead)
    path("provider/<uuid:provider_id>/patient/<uuid:patient_identity_id>/timeline", ProviderPatientTimelineView.as_view()),

    # Provider-facing (consultation panel)
    path("appointment/<str:appointment_id>/patient-summary", ProviderPatientSummaryView.as_view()),

    # Access grant flow
    path("access-request", RecordAccessRequestView.as_view()),
    path("access-grants/<uuid:grant_id>", RecordAccessGrantDetailView.as_view()),

    # Patient sensitivity toggle
    path("sensitivity/<uuid:summary_id>", PatientSensitivityView.as_view()),

    # Records PIN (patient-side)
    path("pin/status", RecordsPinStatusView.as_view()),
    path("pin/set", RecordsPinSetView.as_view()),
    path("pin/verify", RecordsPinVerifyView.as_view()),
    path("pin/change", RecordsPinChangeView.as_view()),
    path("pin/reset", RecordsPinResetView.as_view()),
]
