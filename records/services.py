def find_identity_by_email(email):
    """Look up a patient's Identity by the email given at booking time."""
    if not email:
        return None
    from identity.models import Identity
    return Identity.objects.filter(email__iexact=email).first()


def refresh_record_summary(patient_identity, provider):
    """
    Recompute the lightweight record summary for a (patient_identity,
    provider) pair. Call this after creating or updating an appointment,
    capture, or prescription. Safe to call repeatedly — it recomputes
    from source data rather than incrementing, so it never drifts.
    """
    if not patient_identity or not provider:
        return

    from appointments.models import ProviderAppointment, AppointmentCapture
    from provider.models import Prescription
    from .models import PatientProviderRecordSummary

    appt_qs = ProviderAppointment.objects.filter(
        patient_identity=patient_identity, provider=provider
    ).exclude(status="cancelled")
    appt_count = appt_qs.count()

    capture_count = AppointmentCapture.objects.filter(
        appointment__patient_identity=patient_identity,
        appointment__provider=provider,
    ).count()

    prescription_qs = Prescription.objects.filter(
        patient_identity=patient_identity, provider=provider
    )
    prescription_count = prescription_qs.count()

    total = appt_count + capture_count + prescription_count

    latest_dates = []
    last_appt = appt_qs.order_by("-start_time").first()
    if last_appt:
        latest_dates.append(last_appt.start_time)
    last_prescription = prescription_qs.order_by("-created_at").first()
    if last_prescription:
        latest_dates.append(last_prescription.created_at)
    last_record_at = max(latest_dates) if latest_dates else None

    summary, _ = PatientProviderRecordSummary.objects.get_or_create(
        patient_identity=patient_identity, provider=provider
    )
    summary.record_count = total
    summary.last_record_at = last_record_at
    summary.save(update_fields=["record_count", "last_record_at", "updated_at"])
