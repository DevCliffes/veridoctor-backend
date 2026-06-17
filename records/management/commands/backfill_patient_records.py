from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Backfills patient_identity on existing ProviderAppointment and "
        "Prescription rows by matching patient_email to an Identity, then "
        "rebuilds the PatientProviderRecordSummary index from that data. "
        "Safe to run repeatedly — only touches rows missing the link."
    )

    def handle(self, *args, **options):
        from appointments.models import ProviderAppointment
        from provider.models import Prescription
        from records.services import find_identity_by_email, refresh_record_summary

        appt_linked = 0
        appt_skipped = 0
        with transaction.atomic():
            for appt in ProviderAppointment.objects.filter(patient_identity__isnull=True):
                identity = find_identity_by_email(appt.patient_email)
                if identity:
                    appt.patient_identity = identity
                    appt.save(update_fields=["patient_identity"])
                    appt_linked += 1
                else:
                    appt_skipped += 1

        rx_linked = 0
        rx_skipped = 0
        with transaction.atomic():
            for rx in Prescription.objects.filter(patient_identity__isnull=True):
                identity = find_identity_by_email(rx.patient_email)
                if identity:
                    rx.patient_identity = identity
                    rx.save(update_fields=["patient_identity"])
                    rx_linked += 1
                else:
                    rx_skipped += 1

        self.stdout.write(
            f"Appointments linked: {appt_linked}, skipped (no matching identity): {appt_skipped}"
        )
        self.stdout.write(
            f"Prescriptions linked: {rx_linked}, skipped (no matching identity): {rx_skipped}"
        )

        from identity.models import Identity
        from provider.models import HealthcareProvider

        pairs = set()
        for appt in ProviderAppointment.objects.filter(patient_identity__isnull=False):
            pairs.add((appt.patient_identity_id, appt.provider_id))
        for rx in Prescription.objects.filter(patient_identity__isnull=False):
            pairs.add((rx.patient_identity_id, rx.provider_id))

        rebuilt = 0
        for patient_identity_id, provider_id in pairs:
            patient_identity = Identity.objects.get(id=patient_identity_id)
            provider = HealthcareProvider.objects.get(id=provider_id)
            refresh_record_summary(patient_identity, provider)
            rebuilt += 1

        self.stdout.write(f"Record summaries rebuilt: {rebuilt}")
        self.stdout.write(self.style.SUCCESS("Backfill complete."))
