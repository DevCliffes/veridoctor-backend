from django.urls import path
from .views import PatientRecordSummaryView, PatientTimelineView

urlpatterns = [
    path(
        "patient/<uuid:patient_identity_id>/summary",
        PatientRecordSummaryView.as_view(),
    ),
    path(
        "patient/<uuid:patient_identity_id>/timeline",
        PatientTimelineView.as_view(),
    ),
]
