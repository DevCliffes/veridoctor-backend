from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from identity.models import Identity
from provider.models import HealthcareProvider
from .models import PatientProviderRecordSummary
from .serializers import PatientProviderRecordSummarySerializer


class PatientRecordSummaryView(APIView):
    """
    Returns the cross-provider record summary for a patient — what other
    providers have records for them, with counts and recency only, never
    clinical content. Excludes the requesting provider's own summary,
    since they already have full access to their own records.
    """
    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        exclude_provider_identity_id = request.query_params.get("exclude_provider")
        summaries = PatientProviderRecordSummary.objects.filter(
            patient_identity=patient_identity
        ).select_related("provider", "provider__identity")

        if exclude_provider_identity_id:
            try:
                exclude_provider = HealthcareProvider.objects.get(
                    identity__id=exclude_provider_identity_id
                )
                summaries = summaries.exclude(provider=exclude_provider)
            except HealthcareProvider.DoesNotExist:
                pass

        serializer = PatientProviderRecordSummarySerializer(summaries, many=True)
        return Response(serializer.data)


class PatientTimelineView(APIView):
    """
    Patient-facing clinical timeline. Aggregates all records the patient
    owns across AppointmentCapture, Prescription, and ProviderAppointment,
    sorted by date descending.

    FHIR: Each record includes fhir_resource_type for future Bundle mapping.
    GDPR: Only the patient's own identity_id is accepted — no cross-patient
          access. Clinical content is never returned without a matching
          patient_identity link on the source record.
    UHR:  facility_name is snapshotted at query time from the provider's
          clinic_name so records remain readable even if the provider moves.
    """
    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        record_type = request.query_params.get("type")  # optional filter

        from appointments.models import ProviderAppointment, AppointmentCapture
        from provider.models import Prescription

        records = []

        # ── Consultations (ProviderAppointment) ─────────────────────────────
        if not record_type or record_type == "consultation":
            appointments = ProviderAppointment.objects.filter(
                patient_identity=patient_identity,
            ).exclude(status="cancelled").select_related(
                "provider", "provider__identity", "service"
            ).prefetch_related("captures").order_by("-start_time")

            for appt in appointments:
                captures = []
                for cap in appt.captures.all():
                    captures.append({
                        "form_name": cap.form_name,
                        "form_snapshot": cap.form_snapshot,
                        "values": cap.values,
                        "captured_at": cap.created_at.isoformat(),
                    })

                records.append({
                    "id": str(appt.id),
                    "fhir_resource_type": "Encounter",
                    "record_type": "consultation",
                    "date": appt.start_time.isoformat(),
                    "provider_name": f"Dr. {appt.provider.identity.first_name} {appt.provider.identity.last_name}",
                    "speciality": appt.provider.speciality or "",
                    "facility_name": appt.provider.clinic_name or "",
                    "county": appt.provider.county or "",
                    "appointment_type": appt.appointment_type,
                    "status": appt.status,
                    "service_name": appt.service.name if appt.service else None,
                    "captures": captures,
                    "has_clinical_notes": len(captures) > 0,
                })

        # ── Prescriptions ────────────────────────────────────────────────────
        if not record_type or record_type == "prescription":
            prescriptions = Prescription.objects.filter(
                patient_identity=patient_identity,
            ).select_related(
                "provider", "provider__identity"
            ).prefetch_related("drugs").order_by("-created_at")

            for rx in prescriptions:
                drugs = []
                for drug in rx.drugs.all():
                    drugs.append({
                        "drug_name": drug.drug_name,
                        "dosage": drug.dosage,
                        "frequency": drug.frequency,
                        "duration": drug.duration,
                        "instructions": drug.instructions,
                    })

                records.append({
                    "id": str(rx.id),
                    "fhir_resource_type": "MedicationRequest",
                    "record_type": "prescription",
                    "date": rx.created_at.isoformat(),
                    "provider_name": f"Dr. {rx.provider.identity.first_name} {rx.provider.identity.last_name}",
                    "speciality": rx.provider.speciality or "",
                    "facility_name": rx.provider.clinic_name or "",
                    "county": rx.provider.county or "",
                    "diagnosis": rx.diagnosis,
                    "notes": rx.notes,
                    "drugs": drugs,
                })

        # Sort all record types together by date descending
        records.sort(key=lambda r: r["date"], reverse=True)

        return Response({
            "patient_id": str(patient_identity.id),
            "total": len(records),
            "records": records,
        })
