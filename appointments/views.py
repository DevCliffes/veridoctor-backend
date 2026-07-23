from django.db import transaction
from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField, Count, Sum, Min
from datetime import timedelta
from identity.models import Identity
from provider.models import HealthcareProvider, Prescription, PrescriptionDrug
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ProviderAppointment, AppointmentCapture
from .serializers import ProviderAppointmentSerializer, AppointmentCaptureSerializer
from records.services import find_identity_by_email, refresh_record_summary
from .pagination import AppointmentPagination
from django.db.models.functions import TruncMonth
from django.db.models import Sum, Q as MonthlyQ


# Statuses that occupy a real slot on the calendar — a cancelled or
# no-show appointment shouldn't block someone else from booking that time.
ACTIVE_APPOINTMENT_STATUSES = ["scheduled", "confirmed", "in-progress"]


def _lock_provider_for_booking(provider_id):
    """
    Locks the HealthcareProvider row for the duration of the current
    transaction. This is the actual fix for the double-booking race —
    a plain "check for conflicts, then create" is not safe on its own:
    if no conflicting appointment exists yet, select_for_update() on the
    appointments query has nothing to lock, so two simultaneous requests
    can both pass the check before either one's INSERT commits.

    Locking the provider row instead means the second concurrent request
    to book *this provider* blocks until the first request's transaction
    fully commits or rolls back — so by the time it runs its own overlap
    check, the first booking (if it succeeded) is already visible to it.
    This does serialize all bookings for a single provider, but booking
    volume per provider is low enough that this is not a bottleneck.
    """
    return HealthcareProvider.objects.select_for_update().get(id=provider_id)


def _get_overlapping_appointment(provider, start_time, end_time, exclude_id=None):
    qs = ProviderAppointment.objects.filter(
        provider=provider,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.first()


def _snapshot_price(appointment):
    """
    Copies the current price/currency off appointment.service onto the
    appointment itself, at the moment of booking. This is what makes
    ProviderDashboardStatsView's revenue figures immune to a provider
    later editing (or deleting) their service price list — see
    price_at_booking / currency_at_booking on ProviderAppointment.
    No-ops if the appointment has no service attached.
    """
    service = appointment.service
    if service is not None:
        appointment.price_at_booking = service.price
        appointment.currency_at_booking = service.currency
        appointment.save(update_fields=["price_at_booking", "currency_at_booking"])


def _notify(recipient_identity, notification_type, title, message="", link="", appointment=None, for_provider=False):
    """
    appointment / for_provider: when provided, the email sent alongside
    this notification includes rich appointment details — virtual join
    instructions or in-person address — via
    notifications.services.build_appointment_email_html(). When omitted
    (e.g. prescription-ready notifications with no appointment context),
    falls back to a plain message-only email, same as before.
    """
    try:
        from notifications.services import notify, build_appointment_email_html
        email_html = None
        if appointment is not None:
            email_html = build_appointment_email_html(appointment, for_provider, message)
        notify(
            recipient_identity=recipient_identity,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
            email_html=email_html,
        )
    except Exception:
        pass


def _stamp_actual_times(appointment, old_status, new_status):
    """Record real-world start/end timestamps the moment status actually
    transitions — used to compute true consultation duration, distinct
    from the scheduled start_time/end_time slot. Only stamps on the
    transition itself (old_status != new_status) so re-saving an
    already-in-progress or already-completed appointment doesn't reset
    the clock.

    Fallback: if an appointment is marked completed without ever having
    passed through in-progress (actual_start_time still empty), we use
    the scheduled start_time as a stand-in for actual_start_time rather
    than leaving duration uncomputable — less precise than a real
    in-progress timestamp, but still meaningful.

    That fallback is clamped to `now` via min(): if an appointment is
    force-completed before its scheduled start_time has actually arrived
    (e.g. a future-dated slot completed early for testing/demo purposes),
    using the raw scheduled start_time here would put actual_start_time
    in the future relative to actual_end_time (=now), producing a
    negative duration downstream in ProviderDashboardStatsView's
    "Avg. Duration" calculation. Clamping to whichever is earlier
    guarantees actual_start_time <= now <= actual_end_time."""
    if new_status == old_status:
        return
    now = timezone.now()
    update_fields = []
    if new_status == "in-progress" and not appointment.actual_start_time:
        appointment.actual_start_time = now
        update_fields.append("actual_start_time")
    if new_status == "completed":
        if not appointment.actual_start_time:
            appointment.actual_start_time = min(appointment.start_time, now)
            update_fields.append("actual_start_time")
        if not appointment.actual_end_time:
            appointment.actual_end_time = now
            update_fields.append("actual_end_time")
    if update_fields:
        appointment.save(update_fields=update_fields)


def _extract_prescription_from_capture(capture, appointment):
    try:
        snapshot = capture.form_snapshot or []
        values = capture.values or {}

        if not snapshot or not values:
            return None

        structured = values.get("prescription")
        diagnosis_parts = []
        notes_parts = []
        drug_entries = []

        if isinstance(structured, dict) and structured.get("drugs"):
            if structured.get("diagnosis"):
                diagnosis_parts.append(str(structured["diagnosis"]))
            if structured.get("notes"):
                notes_parts.append(str(structured["notes"]))

            for item in structured["drugs"]:
                if not isinstance(item, dict):
                    continue
                drug_name = str(item.get("drug_name") or item.get("name") or "").strip()
                if not drug_name:
                    continue
                drug_entries.append({
                    "drug_name": drug_name,
                    "dosage": str(item.get("dosage") or "").strip(),
                    "frequency": str(item.get("frequency") or "").strip(),
                    "duration": str(item.get("duration") or "").strip(),
                    "instructions": str(item.get("instructions") or "").strip(),
                })

        if not drug_entries:
            label_map = {}
            for section in snapshot:
                for field in section.get("fields", []):
                    fid = field.get("id")
                    if fid:
                        label_map[fid] = (field.get("label") or field.get("name") or fid).lower()

            PRESCRIPTION_KEYWORDS = {"prescription", "drug", "medication", "dosage", "diagnosis", "medicine"}

            has_prescription_content = any(
                any(kw in label for kw in PRESCRIPTION_KEYWORDS)
                for label in label_map.values()
            )

            if not has_prescription_content and not diagnosis_parts:
                return None

            for field_id, label in label_map.items():
                val = values.get(field_id)
                if not val:
                    continue

                if "diagnosis" in label:
                    diagnosis_parts.append(str(val))
                elif "note" in label or "comment" in label or "remark" in label:
                    notes_parts.append(str(val))
                elif any(kw in label for kw in ("drug", "medication", "medicine", "prescription")):
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                drug_entries.append({
                                    "drug_name": item.get("drug_name") or item.get("name") or item.get("medication") or "Unknown",
                                    "dosage": item.get("dosage") or item.get("dose") or "",
                                    "frequency": item.get("frequency") or item.get("freq") or "",
                                    "duration": item.get("duration") or "",
                                    "instructions": item.get("instructions") or item.get("notes") or "",
                                })
                            else:
                                drug_entries.append({
                                    "drug_name": str(item),
                                    "dosage": "", "frequency": "", "duration": "", "instructions": "",
                                })
                    elif isinstance(val, str) and val.strip() and val.strip().lower() != "none":
                        drug_entries.append({
                            "drug_name": val.strip(),
                            "dosage": "", "frequency": "", "duration": "", "instructions": "",
                        })
                elif "dosage" in label or "dose" in label:
                    if drug_entries:
                        drug_entries[-1]["dosage"] = str(val)
                elif "frequency" in label or "freq" in label:
                    if drug_entries:
                        drug_entries[-1]["frequency"] = str(val)
                elif "duration" in label:
                    if drug_entries:
                        drug_entries[-1]["duration"] = str(val)

        if not diagnosis_parts and not drug_entries:
            return None

        provider = appointment.provider
        patient_identity = appointment.patient_identity
        patient_email = appointment.patient_email or (
            patient_identity.email if patient_identity else ""
        )
        patient_name = f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()

        prescription = Prescription.objects.create(
            provider=provider,
            patient_name=patient_name,
            patient_email=patient_email,
            patient_identity=patient_identity,
            diagnosis=" | ".join(diagnosis_parts),
            notes=" | ".join(notes_parts),
        )

        for drug in drug_entries:
            PrescriptionDrug.objects.create(
                prescription=prescription,
                drug_name=drug["drug_name"],
                dosage=drug["dosage"],
                frequency=drug["frequency"] or "As directed",
                duration=drug["duration"] or "As directed",
                instructions=drug["instructions"],
            )

        if patient_identity:
            provider_name = ""
            if provider and provider.identity:
                pi = provider.identity
                provider_name = f"Dr. {pi.first_name} {pi.last_name}"
            _notify(
                recipient_identity=patient_identity,
                notification_type="prescription_ready",
                title="New prescription issued",
                message=f"{provider_name} has issued a prescription for you.",
                link="/prescriptions",
            )

        return prescription

    except Exception:
        return None


class PatientAppointmentView(APIView):
    def get(self, request):
        patient_email = request.query_params.get("patient_email")
        filter_type = request.query_params.get("filter", "upcoming")

        if not patient_email:
            return Response(
                {"error": "patient_email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        qs = ProviderAppointment.objects.filter(
            patient_email__iexact=patient_email
        ).select_related("provider", "provider__identity", "service")

        if filter_type == "today":
            qs = qs.filter(start_time__date=now.date()).order_by("start_time")
        elif filter_type == "past":
            qs = qs.filter(end_time__lt=now).order_by("-start_time")
        else:
            qs = qs.filter(start_time__gte=now).exclude(
                status__in=["cancelled", "no-show"]
            ).order_by("start_time")

        data = []
        for appt in qs:
            provider = appt.provider
            identity = provider.identity if provider else None
            data.append({
                "id": str(appt.id),
                "doctor_first_name": identity.first_name if identity else "",
                "doctor_last_name": identity.last_name if identity else "",
                "provider_id": str(provider.id) if provider else None,
                "provider_identity_id": str(identity.id) if identity else None,
                "patient_first_name": appt.patient_first_name,
                "patient_last_name": appt.patient_last_name,
                "patient_email": appt.patient_email,
                "patient_phone_number": appt.patient_phone_number,
                "patient_identity": str(appt.patient_identity_id) if appt.patient_identity_id else None,
                "appointment_type": appt.appointment_type,
                "service": str(appt.service_id) if appt.service_id else None,
                "service_name": appt.service.name if appt.service else None,
                "message": appt.message,
                "start_time": appt.start_time.isoformat(),
                "end_time": appt.end_time.isoformat(),
                "status": appt.status,
                "meet_id": appt.meet_id,
                "created_at": appt.created_at.isoformat(),
            })

        return Response(data)

    def post(self, request):
        provider_id = request.data.get("provider")
        if not provider_id:
            return Response({"error": "provider is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provider = HealthcareProvider.objects.get(id=provider_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        if not provider.profile_complete:
            return Response(
                {"error": "This provider is not currently accepting bookings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProviderAppointmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_time = serializer.validated_data["start_time"]
        end_time = serializer.validated_data["end_time"]

        # NOTE: Patients booking themselves through the public booking flow
        # have no "instant" concept — only providers logging walk-ins/express
        # calls do (see ProviderAppointmentView.post below). So this view
        # always enforces the overlap check, unchanged.
        with transaction.atomic():
            _lock_provider_for_booking(provider.id)
            conflict = _get_overlapping_appointment(provider, start_time, end_time)
            if conflict:
                return Response(
                    {"error": "This time slot was just booked by someone else. Please choose another time."},
                    status=status.HTTP_409_CONFLICT,
                )
            appointment = serializer.save(provider=provider)
            _snapshot_price(appointment)

        patient_identity = find_identity_by_email(appointment.patient_email)
        if patient_identity:
            appointment.patient_identity = patient_identity
            appointment.save(update_fields=["patient_identity"])
            refresh_record_summary(patient_identity, appointment.provider)

        if appointment.provider and appointment.provider.identity:
            provider_identity = appointment.provider.identity
            patient_name = f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()
            _notify(
                recipient_identity=provider_identity,
                notification_type="appointment_booked",
                title="New appointment booked",
                message=f"{patient_name} booked an appointment on "
                        f"{appointment.start_time.strftime('%d %b %Y at %H:%M')}.",
                link=f"/appointments/{appointment.id}",
                appointment=appointment,
                for_provider=True,
            )

        if patient_identity:
            provider_name = ""
            if appointment.provider and appointment.provider.identity:
                pi = appointment.provider.identity
                provider_name = f"Dr. {pi.first_name} {pi.last_name}"
            _notify(
                recipient_identity=patient_identity,
                notification_type="appointment_booked",
                title="Appointment confirmed",
                message=f"Your appointment with {provider_name} on "
                        f"{appointment.start_time.strftime('%d %b %Y at %H:%M')} is booked.",
                link="/appointments",
                appointment=appointment,
                for_provider=False,
            )

        return Response(
            ProviderAppointmentSerializer(appointment).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, appointment_id):
        try:
            appointment = ProviderAppointment.objects.select_related(
                "provider", "provider__identity", "patient_identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        old_status = appointment.status
        serializer = ProviderAppointmentSerializer(
            appointment, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = serializer.save()
        new_status = updated.status

        _stamp_actual_times(updated, old_status, new_status)

        patient_identity = updated.patient_identity
        provider_identity = updated.provider.identity if updated.provider else None
        provider_name = ""
        patient_name = f"{updated.patient_first_name} {updated.patient_last_name}".strip()
        if provider_identity:
            pi = provider_identity
            provider_name = f"Dr. {pi.first_name} {pi.last_name}"

        if new_status != old_status:
            if patient_identity:
                if new_status == "confirmed":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_confirmed",
                        title="Appointment confirmed",
                        message=f"Your appointment with {provider_name} has been confirmed.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )
                elif new_status == "cancelled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_cancelled",
                        title="Appointment cancelled",
                        message=f"Your appointment with {provider_name} has been cancelled.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled",
                        message=f"Your appointment with {provider_name} has been rescheduled.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )

            if provider_identity:
                if new_status == "cancelled":
                    _notify(
                        recipient_identity=provider_identity,
                        notification_type="appointment_cancelled",
                        title="Appointment cancelled by patient",
                        message=f"{patient_name} cancelled their appointment on "
                                f"{updated.start_time.strftime('%d %b %Y at %H:%M')}.",
                        link=f"/appointments/{updated.id}",
                        appointment=updated,
                        for_provider=True,
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=provider_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled by patient",
                        message=f"{patient_name} rescheduled their appointment to "
                                f"{updated.start_time.strftime('%d %b %Y at %H:%M')}.",
                        link=f"/appointments/{updated.id}",
                        appointment=updated,
                        for_provider=True,
                    )

        return Response(ProviderAppointmentSerializer(updated).data)


class ProviderAppointmentView(APIView):
    pagination_class = AppointmentPagination

    def get(self, request, identity_id):
        filter_type = request.query_params.get("filter", "upcoming")
        start_param = request.query_params.get("start")
        end_param = request.query_params.get("end")
        now = timezone.now()

        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        # FIX: was missing provider__identity, causing an N+1 -- every row
        # serialized calls appointment.provider.identity.* for
        # provider_first_name/provider_last_name/provider_id (see
        # ProviderAppointmentSerializer), which is 2 extra queries per row
        # without this. patient_identity needs no join: it's a plain FK
        # field on the serializer, rendered as just the id.
        qs = ProviderAppointment.objects.filter(
            provider=provider
        ).select_related("service", "provider__identity")

        if filter_type == "today":
            qs = qs.filter(start_time__date=now.date()).order_by("start_time")
        elif filter_type == "past":
            qs = qs.filter(end_time__lt=now).order_by("-start_time")
        elif filter_type == "all":
            qs = qs.order_by("-start_time")
        else:
            qs = qs.filter(start_time__gte=now).exclude(
                status__in=["cancelled", "no-show"]
            ).order_by("start_time")

        # NEW: optional date-window bounds, used by the Schedule calendar
        # (filter=all) so it isn't forced to pull a provider's entire
        # booking history just to render a ~67-day calendar view.
        if start_param:
            qs = qs.filter(end_time__gte=start_param)
        if end_param:
            qs = qs.filter(start_time__lte=end_param)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        serializer = ProviderAppointmentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        if not provider.profile_complete:
            return Response(
                {"error": "This provider is not currently accepting bookings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data.copy()
        data["provider"] = provider.id

        # "Now" bookings (walk-ins / express virtual calls a provider is
        # taking immediately) are allowed to bypass the normal slot-overlap
        # check, since the whole point is to log an appointment that's
        # already happening regardless of what else is on the calendar.
        # Every other booking path — is_instant absent/false here, and
        # PatientAppointmentView.post above, which has no concept of
        # "instant" at all — still goes through the standard overlap check,
        # unchanged from before.
        is_instant = str(data.pop("is_instant", False)).lower() in ("true", "1")

        serializer = ProviderAppointmentSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_time = serializer.validated_data["start_time"]
        end_time = serializer.validated_data["end_time"]

        if is_instant:
            # Deliberately skip _lock_provider_for_booking and
            # _get_overlapping_appointment here: an instant/walk-in booking
            # is intentionally allowed to land on top of an existing
            # appointment.
            appointment = serializer.save(provider=provider)
        else:
            with transaction.atomic():
                _lock_provider_for_booking(provider.id)
                conflict = _get_overlapping_appointment(provider, start_time, end_time)
                if conflict:
                    return Response(
                        {"error": "This time slot was just booked by someone else. Please choose another time."},
                        status=status.HTTP_409_CONFLICT,
                    )
                appointment = serializer.save(provider=provider)

        _snapshot_price(appointment)

        patient_identity = find_identity_by_email(appointment.patient_email)
        if patient_identity:
            appointment.patient_identity = patient_identity
            appointment.save(update_fields=["patient_identity"])
            refresh_record_summary(patient_identity, provider)

            provider_name = f"Dr. {provider.identity.first_name} {provider.identity.last_name}"

            _notify(
                recipient_identity=patient_identity,
                notification_type="appointment_booked",
                title="Appointment scheduled",
                message=f"{provider_name} has scheduled an appointment for you on "
                        f"{appointment.start_time.strftime('%d %b %Y at %H:%M')}.",
                link="/appointments",
                appointment=appointment,
                for_provider=False,
            )

        if provider and provider.identity:
            patient_name = f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()
            _notify(
                recipient_identity=provider.identity,
                notification_type="appointment_booked",
                title="Appointment added",
                message=f"You scheduled an appointment for {patient_name} on "
                        f"{appointment.start_time.strftime('%d %b %Y at %H:%M')}.",
                link=f"/appointments/{appointment.id}",
                appointment=appointment,
                for_provider=True,
            )

        return Response(
            ProviderAppointmentSerializer(appointment).data,
            status=status.HTTP_201_CREATED,
        )


class ProviderAppointmentDetailView(APIView):
    def get(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.select_related(
                "service", "patient_identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(ProviderAppointmentSerializer(appointment).data)

    def patch(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.select_related(
                "provider", "provider__identity", "patient_identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        old_status = appointment.status
        serializer = ProviderAppointmentSerializer(
            appointment, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = serializer.save()
        new_status = updated.status

        _stamp_actual_times(updated, old_status, new_status)

        patient_identity = updated.patient_identity
        provider_identity = updated.provider.identity if updated.provider else None
        provider_name = ""
        patient_name = f"{updated.patient_first_name} {updated.patient_last_name}".strip()
        if provider_identity:
            pi = provider_identity
            provider_name = f"Dr. {pi.first_name} {pi.last_name}"

        if new_status != old_status:
            if patient_identity:
                if new_status == "confirmed":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_confirmed",
                        title="Appointment confirmed",
                        message=f"Your appointment with {provider_name} has been confirmed.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )
                elif new_status == "cancelled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_cancelled",
                        title="Appointment cancelled",
                        message=f"Your appointment with {provider_name} has been cancelled.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled",
                        message=f"Your appointment with {provider_name} has been rescheduled.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )
                elif new_status == "in-progress":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_confirmed",
                        title="Your consultation has started",
                        message=f"Your consultation with {provider_name} is now in progress.",
                        link="/appointments",
                        appointment=updated,
                        for_provider=False,
                    )

            if provider_identity:
                if new_status == "cancelled":
                    _notify(
                        recipient_identity=provider_identity,
                        notification_type="appointment_cancelled",
                        title="Appointment cancelled",
                        message=f"The appointment with {patient_name} on "
                                f"{updated.start_time.strftime('%d %b %Y at %H:%M')} was cancelled.",
                        link=f"/appointments/{updated.id}",
                        appointment=updated,
                        for_provider=True,
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=provider_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled",
                        message=f"The appointment with {patient_name} has been rescheduled to "
                                f"{updated.start_time.strftime('%d %b %Y at %H:%M')}.",
                        link=f"/appointments/{updated.id}",
                        appointment=updated,
                        for_provider=True,
                    )

        return Response(ProviderAppointmentSerializer(updated).data)

    def delete(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        appointment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AppointmentCaptureView(APIView):
    def get(self, request, identity_id, appointment_id):
        captures = AppointmentCapture.objects.filter(
            appointment_id=appointment_id
        ).order_by("-created_at")

        result = []
        for capture in captures:
            data = AppointmentCaptureSerializer(capture).data

            if not data.get("form_snapshot") and isinstance(data.get("values"), dict):
                smuggled = data["values"].get("__form_snapshot__")
                if smuggled:
                    data["form_snapshot"] = smuggled
                    AppointmentCapture.objects.filter(pk=capture.pk).update(
                        form_snapshot=smuggled
                    )

            result.append(data)

        return Response(result)

    def post(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.select_related(
                "provider", "provider__identity", "patient_identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data["appointment"] = appointment_id

        values = data.get("values", {})
        if isinstance(values, dict) and "__form_snapshot__" in values:
            smuggled = values.pop("__form_snapshot__")
            if not data.get("form_snapshot") and smuggled:
                data["form_snapshot"] = smuggled

        serializer = AppointmentCaptureSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        capture = serializer.save(appointment=appointment)

        if appointment.patient_identity:
            refresh_record_summary(appointment.patient_identity, appointment.provider)

        _extract_prescription_from_capture(capture, appointment)

        return Response(
            AppointmentCaptureSerializer(capture).data,
            status=status.HTTP_201_CREATED,
        )


class ProviderDashboardStatsView(APIView):
    def get(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        today = now.date()

        today_count = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__date=today,
        ).count()

        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        this_week_appointments = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__date__gte=week_start,
            start_time__date__lte=week_end,
        ).count()

        month_start = today.replace(day=1)
        total_patients_month = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__date__gte=month_start,
        ).count()

        completed_qs = ProviderAppointment.objects.filter(
            provider=provider,
            status="completed",
            actual_start_time__isnull=False,
            actual_end_time__isnull=False,
            actual_end_time__gt=F("actual_start_time"),
        ).annotate(
            duration=ExpressionWrapper(
                F("actual_end_time") - F("actual_start_time"), output_field=DurationField()
            )
        )
        avg_duration = completed_qs.aggregate(avg=Avg("duration"))["avg"]
        avg_duration_seconds = round(avg_duration.total_seconds()) if avg_duration else 0

        pending_count = ProviderAppointment.objects.filter(
            provider=provider,
            status__in=["scheduled", "pending"],
            start_time__gte=now,
        ).count()

        # NOTE: sums price_at_booking (a snapshot taken at booking time via
        # _snapshot_price), NOT the live Service.price — so editing or
        # deleting a service later no longer changes past months' reported
        # revenue. See price_at_booking / currency_at_booking on
        # ProviderAppointment.
        revenue_mtd_agg = ProviderAppointment.objects.filter(
            provider=provider,
            status="completed",
            start_time__date__gte=month_start,
            price_at_booking__isnull=False,
        ).aggregate(total=Sum("price_at_booking"))
        revenue_mtd = revenue_mtd_agg["total"] or 0

        # New vs returning patients this month. A patient is "new" if the
        # earliest appointment they've ever had with this provider also
        # falls within the current month — i.e. this month is their first
        # contact. Otherwise they're "returning" (they had at least one
        # appointment with this provider before month_start).
        emails_this_month = set(
            ProviderAppointment.objects.filter(
                provider=provider,
                start_time__date__gte=month_start,
            )
            .exclude(patient_email="")
            .values_list("patient_email", flat=True)
            .distinct()
        )

        new_patients_month = 0
        returning_patients_month = 0

        if emails_this_month:
            first_appointment_by_email = (
                ProviderAppointment.objects.filter(
                    provider=provider,
                    patient_email__in=emails_this_month,
                )
                .values("patient_email")
                .annotate(first_appt=Min("start_time"))
            )

            for row in first_appointment_by_email:
                if row["first_appt"].date() >= month_start:
                    new_patients_month += 1
                else:
                    returning_patients_month += 1

        # Completion rate this month — completed vs no-show vs cancelled.
        # Scheduled/confirmed/in-progress appointments are excluded from
        # the denominator since they haven't resolved to an outcome yet;
        # counting them would understate the rate for the current month
        # while appointments are still in flight.
        status_counts_month = (
            ProviderAppointment.objects.filter(
                provider=provider,
                start_time__date__gte=month_start,
            )
            .values("status")
            .annotate(count=Count("id"))
        )
        status_count_map = {row["status"]: row["count"] for row in status_counts_month}

        completed_count = status_count_map.get("completed", 0)
        no_show_count = status_count_map.get("no-show", 0)
        cancelled_count = status_count_map.get("cancelled", 0)
        completion_denominator = completed_count + no_show_count + cancelled_count
        completion_rate = (
            round((completed_count / completion_denominator) * 100)
            if completion_denominator > 0 else 0
        )

        # Virtual vs in-person split this month, across all statuses (not
        # just completed) — this describes how patients are choosing to
        # book, independent of whether the appointment has happened yet.
        type_counts_month = (
            ProviderAppointment.objects.filter(
                provider=provider,
                start_time__date__gte=month_start,
            )
            .values("appointment_type")
            .annotate(count=Count("id"))
        )
        type_count_map = {row["appointment_type"]: row["count"] for row in type_counts_month}
        virtual_count = type_count_map.get("virtual", 0)
        physical_count = type_count_map.get("physical", 0)

        # Revenue by service this month — same completed + priced-snapshot
        # filter as revenue_mtd above, just grouped instead of summed flat,
        # so revenue_by_service always sums back to revenue_mtd.
        revenue_by_service_qs = (
            ProviderAppointment.objects.filter(
                provider=provider,
                status="completed",
                start_time__date__gte=month_start,
                price_at_booking__isnull=False,
            )
            .values("service__name")
            .annotate(total=Sum("price_at_booking"))
            .order_by("-total")
        )
        revenue_by_service = [
            {"service_name": row["service__name"] or "Unspecified", "revenue": float(row["total"])}
            for row in revenue_by_service_qs
        ]

        DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekly_data = []
        for i in range(6, -1, -1):
            day_date = today - timedelta(days=i)
            count = ProviderAppointment.objects.filter(
                provider=provider,
                start_time__date=day_date,
            ).count()
            weekly_data.append({
                "date": day_date.isoformat(),
                "day": DAY_ABBR[day_date.weekday()],
                "count": count,
            })

        return Response({
            "today_count": today_count,
            "this_week_appointments": this_week_appointments,
            "total_patients_month": total_patients_month,
            "avg_duration_seconds": avg_duration_seconds,
            "pending_count": pending_count,
            "weekly_data": weekly_data,
            "revenue_mtd": float(revenue_mtd),
            "new_patients_month": new_patients_month,
            "returning_patients_month": returning_patients_month,
            "completed_count": completed_count,
            "no_show_count": no_show_count,
            "cancelled_count": cancelled_count,
            "completion_rate": completion_rate,
            "virtual_count": virtual_count,
            "physical_count": physical_count,
            "revenue_by_service": revenue_by_service,
        })

# Add these two view classes to appointments/views.py (same file as
# ProviderAppointmentView, AppointmentCaptureView, etc.), and register the
# URLs alongside your other provider/appointments/* routes:
#
#   path("provider/<uuid:identity_id>/appointments/incomplete-notes",
#        ProviderIncompleteNotesView.as_view()),
#   path("provider/<uuid:identity_id>/appointments/with-messages",
#        ProviderMessagedAppointmentsView.as_view()),
#
# Both reuse HealthcareProvider / ProviderAppointment / AppointmentCapture,
# already imported at the top of this file.

from django.db.models import Q


class ProviderIncompleteNotesView(APIView):
    """
    Appointments that have concluded -- either explicitly marked
    "completed", or past their end_time while still sitting in
    scheduled/confirmed/in-progress (i.e. never resolved) -- but have no
    AppointmentCapture saved against them at all. Deliberately excludes
    appointments still in the future: there's nothing "overdue" about
    notes for a visit that hasn't happened yet, and excludes
    cancelled/no-show/rescheduled, since those were never going to
    produce clinical notes in the first place.
    """
    def get(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        qs = (
            ProviderAppointment.objects.filter(provider=provider)
            .filter(
                Q(status="completed")
                | Q(end_time__lt=now, status__in=["scheduled", "confirmed", "in-progress"])
            )
            .exclude(id__in=AppointmentCapture.objects.values("appointment_id"))
            .order_by("start_time")[:20]
        )

        data = [
            {
                "id": str(a.id),
                "patient_name": f"{a.patient_first_name} {a.patient_last_name}".strip(),
                "appointment_date": a.start_time.isoformat(),
            }
            for a in qs
        ]
        return Response(data)


class ProviderMessagedAppointmentsView(APIView):
    """
    Upcoming appointments (end_time still in the future, not
    cancelled/no-show/completed) that carry a non-empty booking message
    -- the optional "message" field captured at booking time. An item
    naturally drops off this list once the appointment concludes; no
    read/unread tracking needed.
    """
    def get(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        qs = (
            ProviderAppointment.objects.filter(provider=provider, end_time__gte=now)
            .exclude(status__in=["cancelled", "no-show", "completed"])
            .exclude(message="")
            .order_by("start_time")[:20]
        )

        data = [
            {
                "id": str(a.id),
                "patient_name": f"{a.patient_first_name} {a.patient_last_name}".strip(),
                "appointment_date": a.start_time.isoformat(),
                "message": a.message,
            }
            for a in qs
        ]
        return Response(data)

# Add to appointments/views.py, alongside ProviderIncompleteNotesView /
# ProviderMessagedAppointmentsView. Needs one extra import at the top:
#   from django.db.models.functions import TruncMonth
#   from dateutil.relativedelta import relativedelta   # already a Django dep via django-dateutil? if not, use timedelta math below instead




class ProviderMonthlyTrendView(APIView):
    """
    Last N months (default 6) of two independent breakdowns, grouped by
    calendar month of start_time:

      - revenue: completed appointments' price_at_booking summed, vs
        "lost" revenue -- the price_at_booking that would have been
        earned from appointments that ended up cancelled or no-show.
        Both sums rely on price_at_booking surviving status changes,
        which it does (nothing in ProviderAppointment.save() or any
        view clears it on cancellation).
      - appointment_count: split by appointment_type (virtual/physical),
        counted regardless of status -- this describes booking behavior,
        not outcome.

    Response shape:
      [
        {
          "month": "2026-02",
          "completed_revenue": 50000.0,
          "lost_revenue": 8000.0,
          "virtual_count": 44,
          "physical_count": 14
        },
        ...
      ]
    """
    def get(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            months_back = int(request.query_params.get("months", 6))
        except ValueError:
            months_back = 6
        months_back = max(1, min(months_back, 24))

        now = timezone.now()
        # First day of the month, months_back-1 months ago, so "6" means
        # "this month plus the 5 before it" -- matches the weekly_data
        # pattern elsewhere in this file (inclusive of today's period).
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year = current_month_start.year
        month = current_month_start.month - (months_back - 1)
        while month <= 0:
            month += 12
            year -= 1
        range_start = current_month_start.replace(year=year, month=month)

        qs = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__gte=range_start,
        ).annotate(month=TruncMonth("start_time"))

        revenue_rows = (
            qs.filter(price_at_booking__isnull=False)
            .values("month")
            .annotate(
                completed_revenue=Sum(
                    "price_at_booking", filter=MonthlyQ(status="completed")
                ),
                lost_revenue=Sum(
                    "price_at_booking",
                    filter=MonthlyQ(status__in=["cancelled", "no-show"]),
                ),
            )
        )
        revenue_map = {
            row["month"].strftime("%Y-%m"): {
                "completed_revenue": float(row["completed_revenue"] or 0),
                "lost_revenue": float(row["lost_revenue"] or 0),
            }
            for row in revenue_rows
        }

        type_rows = (
            qs.values("month")
            .annotate(
                virtual_count=Count("id", filter=MonthlyQ(appointment_type="virtual")),
                physical_count=Count("id", filter=MonthlyQ(appointment_type="physical")),
            )
        )
        type_map = {
            row["month"].strftime("%Y-%m"): {
                "virtual_count": row["virtual_count"],
                "physical_count": row["physical_count"],
            }
            for row in type_rows
        }

        # Build a complete month sequence so months with zero activity
        # still appear as 0s, keeping the chart's x-axis continuous
        # rather than skipping gaps.
        result = []
        cursor_year, cursor_month = range_start.year, range_start.month
        for _ in range(months_back):
            key = f"{cursor_year:04d}-{cursor_month:02d}"
            rev = revenue_map.get(key, {"completed_revenue": 0.0, "lost_revenue": 0.0})
            typ = type_map.get(key, {"virtual_count": 0, "physical_count": 0})
            result.append({
                "month": key,
                **rev,
                **typ,
            })
            cursor_month += 1
            if cursor_month > 12:
                cursor_month = 1
                cursor_year += 1

        return Response(result)
