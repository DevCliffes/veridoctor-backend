from django.urls import path
from .views import PatientRecordSummaryView

urlpatterns = [
    path(
        "patient/<uuid:patient_identity_id>/summary",
        PatientRecordSummaryView.as_view(),
    ),
]
