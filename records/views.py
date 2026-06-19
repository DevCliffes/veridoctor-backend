from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from identity.models import Identity
from provider.models import HealthcareProvider
from .models import PatientProviderRecordSummary, RecordAccessGrant
from .serializers import PatientProviderRecordSummarySerializer


class PatientRecordSummaryView(APIView):
    """
    Returns the cross-provider record summary for a patient — counts and
    recency only, never clinical content.
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
    Patient-facing clinical timeline across AppointmentCapture,
    Prescription, and ProviderAppointment.
    """
    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        record_type = request.query_params.get("type")

        from appointments.models import ProviderAppointment, AppointmentCapture
        from provider.models import Prescription

        records = []

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

        records.sort(key=lambda r: r["date"], reverse=True)

        return Response({
            "patient_id": str(patient_identity.id),
            "total": len(records),
            "records": records,
        })


class ProviderPatientSummaryView(APIView):
    """
    Provider-facing patient record panel shown during a consultation.
    Returns patient profile, stats, always-visible data (allergies,
    active meds), record categories from other providers with consent
    status, and access grants for this consultation.
    """
    def get(self, request, appointment_id):
        from appointments.models import ProviderAppointment
        from provider.models import Prescription

        try:
            appointment = ProviderAppointment.objects.select_related(
                "patient_identity", "provider", "provider__identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        patient_identity = appointment.patient_identity
        if not patient_identity:
            return Response(
                {"error": "No patient identity linked to this appointment"},
                status=status.HTTP_404_NOT_FOUND,
            )

        requesting_provider = appointment.provider

        # Patient profile — from patientAccount
        try:
            from identity.models import patientAccount
            patient_acct = patientAccount.objects.get(identity=patient_identity)
            patient_uid = patient_acct.patient_uid
            date_of_birth = (
                patient_acct.date_of_birth.isoformat()
                if patient_acct.date_of_birth
                else None
            )
            blood_type = patient_acct.blood_type
            allergies = patient_acct.allergies or []
        except Exception:
            patient_uid = None
            date_of_birth = None
            blood_type = None
            allergies = []

        # Stats from PatientProviderRecordSummary
        summaries = PatientProviderRecordSummary.objects.filter(
            patient_identity=patient_identity
        ).select_related("provider", "provider__identity")

        total_records = sum(s.record_count for s in summaries)
        last_dates = [s.last_record_at for s in summaries if s.last_record_at]
        most_recent = max(last_dates).isoformat() if last_dates else None
        prior_facilities = summaries.count()

        # Active medications
        active_meds = Prescription.objects.filter(
            patient_identity=patient_identity
        ).count()

        # Record categories — exclude the requesting provider's own records
        other_summaries = summaries.exclude(provider=requesting_provider)

        # Access grants for this specific consultation
        grants = RecordAccessGrant.objects.filter(
            appointment=appointment,
            patient_identity=patient_identity,
        )
        grants_by_category = {g.requested_category: g for g in grants}

        record_categories = []
        for s in other_summaries:
            category_key = s.provider.speciality or s.provider.clinic_name or "General"
            grant = grants_by_category.get(category_key)
            record_categories.append({
                "speciality": s.provider.speciality or "General Practice",
                "facility_name": s.provider.clinic_name or "",
                "record_count": s.record_count,
                "last_record_at": s.last_record_at.isoformat() if s.last_record_at else None,
                "sensitivity": s.sensitivity,
                "access_status": grant.status if grant else None,
                "grant_id": str(grant.id) if grant else None,
            })

        approved_grants = [
            {
                "id": str(g.id),
                "requested_category": g.requested_category,
                "status": g.status,
                "responded_at": g.responded_at.isoformat() if g.responded_at else None,
            }
            for g in grants
            if g.status == "approved"
        ]

        return Response({
            "patient": {
                "uid": patient_uid,
                "identity_id": str(patient_identity.id),
                "first_name": patient_identity.first_name,
                "last_name": patient_identity.last_name,
                "gender": patient_identity.gender or "UNKNOWN",
                "date_of_birth": date_of_birth,
                "blood_type": blood_type,
            },
            "consultation_active": appointment.status in ["confirmed", "in-progress"],
            "stats": {
                "total_records": total_records,
                "most_recent": most_recent,
                "active_medications": active_meds,
                "prior_facilities": prior_facilities,
            },
            "always_visible": {
                "allergies": allergies,
                "active_medications_count": active_meds,
            },
            "record_categories": record_categories,
            "access_granted": approved_grants,
        })


class RecordAccessRequestView(APIView):
    """
    Provider requests access to a patient's records for a specific category.
    Patient is notified in the health portal and must approve.
    """
    def post(self, request):
        from appointments.models import ProviderAppointment

        appointment_id = request.data.get("appointment_id")
        requested_category = request.data.get("requested_category")
        provider_identity_id = request.data.get("provider_identity_id")

        if not all([appointment_id, requested_category, provider_identity_id]):
            return Response(
                {"error": "appointment_id, requested_category, and provider_identity_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
            provider = HealthcareProvider.objects.get(identity__id=provider_identity_id)
        except (ProviderAppointment.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Appointment or provider not found"}, status=status.HTTP_404_NOT_FOUND)

        patient_identity = appointment.patient_identity
        if not patient_identity:
            return Response(
                {"error": "No patient identity linked to this appointment"},
                status=status.HTTP_404_NOT_FOUND,
            )

        grant, created = RecordAccessGrant.objects.get_or_create(
            patient_identity=patient_identity,
            requesting_provider=provider,
            appointment=appointment,
            requested_category=requested_category,
            defaults={"status": "pending"},
        )

        # Allow re-requesting if previously denied
        if not created and grant.status == "denied":
            grant.status = "pending"
            grant.responded_at = None
            grant.save(update_fields=["status", "responded_at", "updated_at"])

        return Response(
            {
                "id": str(grant.id),
                "requested_category": grant.requested_category,
                "status": grant.status,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PatientAccessRequestsView(APIView):
    """
    Patient sees all access requests made against their records.
    GET /records/patient/<patient_identity_id>/access-requests
    """
    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        grants = RecordAccessGrant.objects.filter(
            patient_identity=patient_identity,
        ).select_related(
            "requesting_provider",
            "requesting_provider__identity",
            "appointment",
        ).order_by("-created_at")

        data = [
            {
                "id": str(g.id),
                "requested_category": g.requested_category,
                "status": g.status,
                "provider_name": (
                    f"Dr. {g.requesting_provider.identity.first_name} "
                    f"{g.requesting_provider.identity.last_name}"
                ),
                "provider_speciality": g.requesting_provider.speciality or "",
                "facility_name": g.requesting_provider.clinic_name or "",
                "appointment_date": g.appointment.start_time.isoformat(),
                "created_at": g.created_at.isoformat(),
                "responded_at": g.responded_at.isoformat() if g.responded_at else None,
            }
            for g in grants
        ]

        return Response(data)


class RecordAccessGrantDetailView(APIView):
    """
    Patient approves or denies an access request.
    PATCH /records/access-grants/<grant_id>
    """
    def patch(self, request, grant_id):
        new_status = request.data.get("status")
        if new_status not in ("approved", "denied"):
            return Response(
                {"error": "status must be 'approved' or 'denied'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            grant = RecordAccessGrant.objects.get(id=grant_id)
        except RecordAccessGrant.DoesNotExist:
            return Response({"error": "Grant not found"}, status=status.HTTP_404_NOT_FOUND)

        grant.status = new_status
        grant.responded_at = timezone.now()
        grant.save(update_fields=["status", "responded_at", "updated_at"])

        return Response({
            "id": str(grant.id),
            "status": grant.status,
            "responded_at": grant.responded_at.isoformat(),
        })
