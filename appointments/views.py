from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField, Count, Sum
from datetime import timedelta
from identity.models import Identity
from provider.models import HealthcareProvider, Prescription, PrescriptionDrug
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ProviderAppointment, AppointmentCapture
from .serializers import ProviderAppointmentSerializer, AppointmentCaptureSerializer
from records.services import find_identity_by_email, refresh_record_summary


def _notify(recipient_identity, notification_type, title, message="", link=""):
    try:
        from notifications.models import Notification
        Notification.objects.create(
            recipient_identity=recipient_identity,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
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
        if provider_id:
            try:
                provider = HealthcareProvider.objects.get(id=provider_id)
            except HealthcareProvider.DoesNotExist:
                return Response(
                    {"error": "Provider not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not provider.profile_complete:
                return Response(
                    {"error": "This provider is not currently accepting bookings."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = ProviderAppointmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        appointment = serializer.save()

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
                    )
                elif new_status == "cancelled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_cancelled",
                        title="Appointment cancelled",
                        message=f"Your appointment with {provider_name} has been cancelled.",
                        link="/appointments",
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled",
                        message=f"Your appointment with {provider_name} has been rescheduled.",
                        link="/appointments",
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
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=provider_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled by patient",
                        message=f"{patient_name} rescheduled their appointment to "
                                f"{updated.start_time.strftime('%d %b %Y at %H:%M')}.",
                        link=f"/appointments/{updated.id}",
                    )

        return Response(ProviderAppointmentSerializer(updated).data)


class ProviderAppointmentView(APIView):
    def get(self, request, identity_id):
        filter_type = request.query_params.get("filter", "upcoming")
        now = timezone.now()

        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        qs = ProviderAppointment.objects.filter(
            provider=provider
        ).select_related("service")

        if filter_type == "today":
            qs = qs.filter(start_time__date=now.date()).order_by("start_time")
        elif filter_type == "past":
            qs = qs.filter(end_time__lt=now).order_by("-start_time")
        elif filter_type == "all":
            qs = qs.order_by("start_time")
        else:
            qs = qs.filter(start_time__gte=now).exclude(
                status__in=["cancelled", "no-show"]
            ).order_by("start_time")

        serializer = ProviderAppointmentSerializer(qs, many=True)
        return Response(serializer.data)

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

        serializer = ProviderAppointmentSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        appointment = serializer.save(provider=provider)

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
                    )
                elif new_status == "cancelled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_cancelled",
                        title="Appointment cancelled",
                        message=f"Your appointment with {provider_name} has been cancelled.",
                        link="/appointments",
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled",
                        message=f"Your appointment with {provider_name} has been rescheduled.",
                        link="/appointments",
                    )
                elif new_status == "in-progress":
                    _notify(
                        recipient_identity=patient_identity,
                        notification_type="appointment_confirmed",
                        title="Your consultation has started",
                        message=f"Your consultation with {provider_name} is now in progress.",
                        link="/appointments",
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
                    )
                elif new_status == "rescheduled":
                    _notify(
                        recipient_identity=provider_identity,
                        notification_type="appointment_rescheduled",
                        title="Appointment rescheduled",
                        message=f"The appointment with {patient_name} has been rescheduled to "
                                f"{updated.start_time.strftime('%d %b %Y at %H:%M')}.",
                        link=f"/appointments/{updated.id}",
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

        # actual_end_time__gt=F("actual_start_time") is a defensive guard:
        # it excludes any row where the "actual" timestamps are backwards
        # or equal, so a single bad/legacy row (e.g. from an appointment
        # force-completed before its scheduled time, pre-dating the fix in
        # _stamp_actual_times above) can never drag the average negative
        # or otherwise nonsensical again.
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
        # Returned in whole seconds rather than pre-rounded to minutes: with
        # short test/demo consultations (a few seconds each), rounding to
        # the nearest minute collapses a real, non-zero average down to 0,
        # which the dashboard then can't distinguish from "no data yet."
        # Keeping seconds preserves that precision; the frontend formats it
        # as minutes+seconds (e.g. "1m 12s" or "45s") instead of losing it.
        avg_duration_seconds = round(avg_duration.total_seconds()) if avg_duration else 0
...
"avg_duration_seconds": avg_duration_seconds,

        pending_count = ProviderAppointment.objects.filter(
            provider=provider,
            status__in=["scheduled", "pending"],
            start_time__gte=now,
        ).count()

        revenue_mtd_agg = ProviderAppointment.objects.filter(
            provider=provider,
            status="completed",
            start_time__date__gte=month_start,
            service__price__isnull=False,
        ).aggregate(total=Sum("service__price"))
        revenue_mtd = revenue_mtd_agg["total"] or 0

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
        })
