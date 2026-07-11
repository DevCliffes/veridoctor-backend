from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("encounters", views.EncounterViewSet, basename="encounter")
router.register("vitals", views.VitalSignsViewSet, basename="vitalsigns")
router.register("clinical-notes", views.ClinicalNoteViewSet, basename="clinicalnote")
router.register("diagnoses", views.DiagnosisViewSet, basename="diagnosis")
router.register("medication-orders", views.MedicationOrderViewSet, basename="medicationorder")
router.register("lab-orders", views.LabOrderViewSet, basename="laborder")
router.register("invoices", views.InvoiceViewSet, basename="invoice")
router.register("access-logs", views.PatientRecordAccessLogViewSet, basename="patientrecordaccesslog")

urlpatterns = router.urls
