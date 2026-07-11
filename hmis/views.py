"""
API viewsets. Every viewset touching patient data:
  1. Scopes get_queryset() to what this user is allowed to see (defense in
     depth alongside the object-level permission classes).
  2. Calls hmis.audit.log_access on retrieve/list/create/update so
     PatientRecordAccessLog reflects reality, not just intent.

If you add a new endpoint that reads or writes clinical/billing data,
follow this same pattern — don't bypass log_access "just this once".
"""

import os

from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models, serializers
from .audit import log_access
from .permissions import CanAccessEncounter, CanAccessPatientRecord


class BaseEncounterScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, CanAccessEncounter]
    encounter_field = "encounter"

    def get_patient(self, obj):
        encounter = getattr(obj, self.encounter_field, obj)
        return encounter.patient

    def _visible_encounter_ids(self, user):
        return models.Encounter.objects.filter(
            Q(patient__identity=user)
            | Q(provider__identity=user)
            | Q(facility__owner__identity=user)
            | Q(facility__managers__identity=user)
            | Q(facility__workstations__assigned_staff=user)
        ).values_list("id", flat=True).distinct()

    def get_queryset(self):
        qs = super().get_queryset()
        encounter_ids = self._visible_encounter_ids(self.request.user)
        filter_kwargs = {f"{self.encounter_field}__id__in": encounter_ids}
        return qs.filter(**filter_kwargs)

    def perform_action_log(self, instance, action):
        log_access(
            patient=self.get_patient(instance),
            accessed_by=self.request.user,
            action=action,
            resource=f"{instance.__class__.__name__}:{instance.pk}",
            request=self.request,
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self.perform_action_log(self.get_object(), "VIEW")
        return response

    def perform_create(self, serializer):
        instance = serializer.save()
        self.perform_action_log(instance, "CREATE")

    def perform_update(self, serializer):
        instance = serializer.save()
        self.perform_action_log(instance, "UPDATE")


class EncounterViewSet(BaseEncounterScopedViewSet):
    queryset = models.Encounter.objects.all()
    serializer_class = serializers.EncounterSerializer
    encounter_field = "id"  # self-referential: the object IS the encounter

    def get_patient(self, obj):
        return obj.patient

    def get_queryset(self):
        user = self.request.user
        return models.Encounter.objects.filter(
            Q(patient__identity=user)
            | Q(provider__identity=user)
            | Q(facility__owner__identity=user)
            | Q(facility__managers__identity=user)
            | Q(facility__workstations__assigned_staff=user)
        ).distinct()


class VitalSignsViewSet(BaseEncounterScopedViewSet):
    queryset = models.VitalSigns.objects.all()
    serializer_class = serializers.VitalSignsSerializer

    def perform_create(self, serializer):
        instance = serializer.save(recorded_by=self.request.user)
        self.perform_action_log(instance, "CREATE")


class ClinicalNoteViewSet(BaseEncounterScopedViewSet):
    queryset = models.ClinicalNote.objects.all()
    serializer_class = serializers.ClinicalNoteSerializer

    def perform_create(self, serializer):
        provider = getattr(self.request.user, "healthcareprovideraccount", None)
        instance = serializer.save(author=provider)
        self.perform_action_log(instance, "CREATE")


class DiagnosisViewSet(BaseEncounterScopedViewSet):
    queryset = models.Diagnosis.objects.all()
    serializer_class = serializers.DiagnosisSerializer

    def perform_create(self, serializer):
        provider = getattr(self.request.user, "healthcareprovideraccount", None)
        instance = serializer.save(diagnosed_by=provider)
        self.perform_action_log(instance, "CREATE")


class MedicationOrderViewSet(BaseEncounterScopedViewSet):
    queryset = models.MedicationOrder.objects.all()
    serializer_class = serializers.MedicationOrderSerializer

    def perform_create(self, serializer):
        provider = getattr(self.request.user, "healthcareprovideraccount", None)
        instance = serializer.save(prescribed_by=provider)
        self.perform_action_log(instance, "CREATE")


class LabOrderViewSet(BaseEncounterScopedViewSet):
    queryset = models.LabOrder.objects.all()
    serializer_class = serializers.LabOrderSerializer

    def perform_create(self, serializer):
        provider = getattr(self.request.user, "healthcareprovideraccount", None)
        instance = serializer.save(ordered_by=provider)
        self.perform_action_log(instance, "CREATE")

    def get_patient(self, obj):
        return obj.encounter.patient


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = models.Invoice.objects.all()
    serializer_class = serializers.InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated, CanAccessPatientRecord]

    def get_queryset(self):
        user = self.request.user
        return models.Invoice.objects.filter(
            Q(patient__identity=user)
            | Q(facility__owner__identity=user)
            | Q(facility__managers__identity=user)
            | Q(facility__workstations__assigned_staff=user)
        ).distinct()

    def perform_create(self, serializer):
        instance = serializer.save()
        log_access(
            patient=instance.patient, accessed_by=self.request.user,
            action="CREATE", resource=f"Invoice:{instance.pk}", request=self.request,
        )


class PatientRecordAccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only — nothing ever writes here except hmis.audit.log_access."""

    queryset = models.PatientRecordAccessLog.objects.all()
    serializer_class = serializers.PatientRecordAccessLogSerializer
    permission_classes = [permissions.IsAuthenticated, CanAccessPatientRecord]

    def get_queryset(self):
        user = self.request.user
        return models.PatientRecordAccessLog.objects.filter(
            Q(patient__identity=user)
            | Q(patient__encounters__facility__owner__identity=user)
            | Q(patient__encounters__facility__managers__identity=user)
        ).distinct()


class LabResultFileUploadView(APIView):
    """
    Uploads a lab result file straight to Cloudinary and stores only the
    resulting secure_url on LabResult.result_file. The file is never
    written to local disk — this service's filesystem is ephemeral, so a
    Django FileField writing to MEDIA_ROOT would silently lose the file on
    the next deploy/restart. Mirrors provider.views.ProviderGenericImageUploadView.
    """
    permission_classes = [IsAuthenticated, CanAccessPatientRecord]
    parser_classes = [MultiPartParser]

    def post(self, request, lab_result_id):
        import cloudinary
        import cloudinary.uploader

        try:
            lab_result = models.LabResult.objects.select_related(
                "lab_order__encounter__patient"
            ).get(id=lab_result_id)
        except models.LabResult.DoesNotExist:
            return Response({"error": "Lab result not found"}, status=status.HTTP_404_NOT_FOUND)

        patient = lab_result.lab_order.encounter.patient
        self.check_object_permissions(request, patient)

        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
        api_key = os.environ.get("CLOUDINARY_API_KEY")
        api_secret = os.environ.get("CLOUDINARY_API_SECRET")
        if not all([cloud_name, api_key, api_secret]):
            return Response(
                {"error": "Cloudinary not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)

        try:
            result = cloudinary.uploader.upload(
                file,
                folder=f"veridoctor/labresults/{patient.id}",
                public_id=str(lab_result.id),
                overwrite=True,
                resource_type="auto",
            )
        except Exception as e:
            return Response({"error": f"Upload failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        url = result.get("secure_url")
        if not url:
            return Response({"error": "No URL returned from Cloudinary"}, status=status.HTTP_502_BAD_GATEWAY)

        lab_result.result_file = url
        lab_result.save(update_fields=["result_file"])

        log_access(
            patient=patient,
            accessed_by=request.user,
            action="UPDATE",
            resource=f"LabResult:{lab_result.pk}",
            request=request,
        )

        return Response({"result_file": url}, status=status.HTTP_200_OK)
