from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField
from identity.models import Identity
from provider.models import HealthcareProvider
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from datetime import timedelta

from records.services import find_identity_by_email, refresh_record_summary
from notifications.services import notify

from .models import AppointmentCapture, ProviderAppointment
from .serializers import AppointmentCaptureSerializer, ProviderAppointmentSerializer


def auto_advance_status(appointment):
    """
    Automatically advance appointment status based on time:
    - Any newly created appointment defaults to 'confirmed' (handled at model level).
    - If status is 'confirmed' and current time is within the appointment window,
      advance to 'in-progress'.
    - If status is 'in-progress' and the appointment end time has passed,
      advance to 'completed'.
    This is called on every GET of a single appointment so it stays current
    without needing a background job.
    """
    now = timezone.now()
    changed = False

    if appointment.status == "confirmed" and appointment.start_time <= now <= appointment.end_time:
        appointment.status = "in-progress"
        changed = True
    elif appointment.status in ("confirmed", "in-progress") and appointment.end_time < now:
        appointment.status = "completed"
        changed = True

    if changed:
        appointment.save(update_fields=["status"])

    return appointment


def _patient_display_name(appointment):
    name = f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()
    return name or "A patient"


def _provider_display_name(provider):
    try:
        return f"Dr. {provider.identity.first_name} {provider.identity.last_name}".strip()
    except Exception:
        return "Your provider"


class ProviderAppointmentView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        appointments = ProviderAppointment.objects.filter(provider=provider)
        now = timezone.now()

        filter_type = request.query_params.get("filter")
        appointment_type = request.query_params.get("appointment_type")

        if filter_type == "today":
            appointments = appointments.filter(
                start_time__date=now.astimezone(timezone.get_current_timezone()).date()
            )
            appointments = appointments.order_by("start_time")
        elif filter_type == "upcoming":
            appointments = appointments.filter(start_time__gt=now)
            appointments = appointments.order_by("start_time")
        elif filter_type == "past":
            appointments = appointments.filter(start_time__lt=now)
            appointments = appointments.order_by("-start_time")
        else:
            appointments = appointments.order_by("start_time")

        if appointment_type:
            appointments = appointments.filter(appointment_type=appointment_type)

        serializer = ProviderAppointmentSerializer(appointments, many=True)
        return Response(serializer.data)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        patient_email = (request.data.get("patient_email") or "").strip()
        if not patient_email:
            return Response(
                {"error": "patient_email is required to book an appointment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Force status to confirmed on creation regardless of what was sent
        data = {**request.data, "patient_email": patient_email, "status": "confirmed"}
        serializer = ProviderAppointmentSerializer(data=data)
        if serializer.is_valid():
            patient_identity = find_identity_by_email(patient_email)
            appointment = serializer.save(provider=provider, patient_identity=patient_identity)
            refresh_record_summary(patient_identity, provider)

            # Notify the patient, if they have a linked account. Booking can
            # happen with just an email (no account yet), so this is None-safe.
            notify(
                recipient_identity=patient_identity,
                notification_type="appointment_booked",
                title="Appointment confirmed",
                message=f"Your appointment with {_provider_display_name(provider)} "
                        f"is confirmed for {appointment.start_time.strftime('%b %d, %Y at %H:%M')}.",
                link=f"/appointments/{appointment.id}",
            )

            return Response(ProviderAppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProviderAppointmentDetailView(APIView):
    def get(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        # Auto-advance status based on current time before returning
        appointment = auto_advance_status(appointment)

        serializer = ProviderAppointmentSerializer(appointment)
        return Response(serializer.data)

    def patch(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        # Prevent manually setting confirmed or in-progress — those are automatic
        incoming_status = request.data.get("status")
        if incoming_status in ("confirmed", "in-progress"):
            return Response(
                {"error": "This status is set automatically and cannot be manually assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine what's actually changing before saving, so we know which
        # notification (if any) to send — and so the "rescheduled" message
        # can mention the new time, and "cancelled" doesn't also fire as if
        # it were a reschedule.
        is_being_cancelled = incoming_status == "cancelled" and appointment.status != "cancelled"
        is_being_rescheduled = (
            not is_being_cancelled
            and ("start_time" in request.data or "end_time" in request.data)
        )

        serializer = ProviderAppointmentSerializer(appointment, data=request.data, partial=True)
        if serializer.is_valid():
            updated_appointment = serializer.save()

            # This PATCH is provider-initiated (it's under the provider/<id>/
            # appointments/<id> route), so the notification goes to the patient.
            if is_being_cancelled and updated_appointment.patient_identity:
                notify(
                    recipient_identity=updated_appointment.patient_identity,
                    notification_type="appointment_cancelled",
                    title="Appointment cancelled",
                    message=f"Your appointment with "
                            f"{_provider_display_name(updated_appointment.provider)} "
                            f"on {updated_appointment.start_time.strftime('%b %d, %Y at %H:%M')} "
                            f"has been cancelled.",
                    link=f"/appointments/{updated_appointment.id}",
                )
            elif is_being_rescheduled and updated_appointment.patient_identity:
                notify(
                    recipient_identity=updated_appointment.patient_identity,
                    notification_type="appointment_rescheduled",
                    title="Appointment rescheduled",
                    message=f"Your appointment with "
                            f"{_provider_display_name(updated_appointment.provider)} "
                            f"has been moved to "
                            f"{updated_appointment.start_time.strftime('%b %d, %Y at %H:%M')}.",
                    link=f"/appointments/{updated_appointment.id}",
                )

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)
        appointment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AppointmentCaptureView(APIView):
    def get(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        captures = AppointmentCapture.objects.filter(appointment=appointment)
        serializer = AppointmentCaptureSerializer(captures, many=True)
        return Response(serializer.data)

    def post(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        from provider.models import Form
        form_snapshot = []
        form_id = request.data.get("form_id")
        if form_id:
            try:
                form = Form.objects.get(id=form_id)
                form_snapshot = form.sections
            except Form.DoesNotExist:
                pass

        data = {**request.data, "form_snapshot": form_snapshot}
        serializer = AppointmentCaptureSerializer(data=data)
        if serializer.is_valid():
            capture = serializer.save(appointment=appointment)
            refresh_record_summary(appointment.patient_identity, appointment.provider)
            return Response(AppointmentCaptureSerializer(capture).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProviderDashboardStatsView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        local_now = now.astimezone(timezone.get_current_timezone())
        today = local_now.date()

        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_qs = ProviderAppointment.objects.filter(provider=provider)

        today_qs = base_qs.filter(start_time__date=today)
        today_count = today_qs.count()

        upcoming_today = today_qs.filter(
            start_time__gt=now,
            status__in=["scheduled", "confirmed"]
        ).count()

        pending_count = base_qs.filter(status="scheduled").count()

        week_qs = base_qs.filter(start_time__gte=week_start, start_time__lt=week_end)
        this_week_appointments = week_qs.count()
        this_week_patients = week_qs.values("patient_email").distinct().count()

        month_qs = base_qs.filter(start_time__gte=month_start)
        total_patients_month = month_qs.exclude(status="cancelled").count()

        month_with_duration = month_qs.exclude(status="cancelled").annotate(
            duration=ExpressionWrapper(
                F("end_time") - F("start_time"), output_field=DurationField()
            )
        )
        avg_duration_td = month_with_duration.aggregate(avg=Avg("duration"))["avg"]
        avg_duration_minutes = int(avg_duration_td.total_seconds() / 60) if avg_duration_td else 0

        weekly_data = []
        for i in range(6, -1, -1):
            day = (local_now - timedelta(days=i)).date()
            count = base_qs.filter(start_time__date=day).count()
            weekly_data.append({
                "date": day.isoformat(),
                "day": day.strftime("%a"),
                "count": count,
            })

        return Response({
            "today_count": today_count,
            "upcoming_today": upcoming_today,
            "pending_count": pending_count,
            "this_week_appointments": this_week_appointments,
            "this_week_patients": this_week_patients,
            "total_patients_month": total_patients_month,
            "avg_duration_minutes": avg_duration_minutes,
            "weekly_data": weekly_data,
        })


class PatientAppointmentView(APIView):
    def get(self, request):
        patient_email = request.query_params.get("patient_email")
        if not patient_email:
            return Response(
                {"error": "patient_email query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        appointments = ProviderAppointment.objects.filter(patient_email=patient_email)
        now = timezone.now()
        today = now.astimezone(timezone.get_current_timezone()).date()
        filter_type = request.query_params.get("filter", "upcoming")

        if filter_type == "today":
            appointments = appointments.filter(start_time__date=today)
        elif filter_type == "past":
            appointments = appointments.filter(start_time__lt=now)
        else:
            appointments = appointments.filter(start_time__gte=now)

        appointments = appointments.order_by("start_time")
        serializer = ProviderAppointmentSerializer(appointments, many=True)
        return Response(serializer.data)

    def patch(self, request):
        appointment_id = request.query_params.get("appointment_id")
        if not appointment_id:
            return Response(
                {"error": "appointment_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        appointment.status = "cancelled"
        appointment.save()

        # This PATCH is patient-initiated, so the notification goes to the
        # provider. provider.identity is reached via the existing FK — no
        # new query needed.
        try:
            provider_identity = appointment.provider.identity
        except Exception:
            provider_identity = None

        notify(
            recipient_identity=provider_identity,
            notification_type="appointment_cancelled",
            title="Appointment cancelled",
            message=f"{_patient_display_name(appointment)} cancelled their "
                    f"appointment scheduled for "
                    f"{appointment.start_time.strftime('%b %d, %Y at %H:%M')}.",
            link=f"/appointments/{appointment.id}",
        )

        serializer = ProviderAppointmentSerializer(appointment)
        return Response(serializer.data)
