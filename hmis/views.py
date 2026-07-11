"""
API viewsets. Every viewset touching patient data:
  1. Scopes get_queryset() to what this user is allowed to see (defense in
     depth alongside the object-level permission classes).
  2. Calls hmis.audit.log_access on retrieve/list/create/update so
     PatientRecordAccessLog reflects reality, not just intent.

If you add a new endpoint that reads or writes clinical/billing data,
follow this same pattern — don't bypass log_access "just this once".
"""

from django.db.models import Q
from rest_framework import viewsets, permissions

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
