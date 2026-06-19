from django.urls import path
from .views import DebugPatientSummaryView
from .views import (
    PatientRecordSummaryView,
    PatientTimelineView,
    ProviderPatientSummaryView,
    RecordAccessRequestView,
    PatientAccessRequestsView,
    RecordAccessGrantDetailView,
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
    path("debug-patient-summary/<str:appointment_id>", DebugPatientSummaryView.as_view()),
    path("access-grants/<uuid:grant_id>", RecordAccessGrantDetailView.as_view()),
]
