from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField, Count
from datetime import timedelta
from identity.models import Identity
from provider.models import HealthcareProvider
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
        ).select_related("provider", "provider__identity", "service").order_by("start_time")

        if filter_type == "today":
            qs = qs.filter(start_time__date=now.date())
        elif filter_type == "past":
            qs = qs.filter(end_time__lt=now)
        else:
            qs = qs.filter(start_time__gte=now).exclude(
                status__in=["cancelled", "no-show"]
            )

        data = []
        for appt in qs:
            provider = appt.provider
            identity = provider.identity if provider else None
            data.append({
                "id": str(appt.id),
                "doctor_first_name": identity.first_name if identity else "",
                "doctor_last_name": identity.last_name if identity else "",
                "provider_id": str(provider.id) if provider else None,
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

        patient_identity = updated.patient_identity
        provider_name = ""
        if updated.provider and updated.provider.identity:
            pi = updated.provider.identity
            provider_name = f"Dr. {pi.first_name} {pi.last_name}"

        if patient_identity and new_status != old_status:
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
        ).select_related("service").order_by("start_time")

        if filter_type == "today":
            qs = qs.filter(start_time__date=now.date())
        elif filter_type == "past":
            qs = qs.filter(end_time__lt=now)
        elif filter_type == "all":
            pass
        else:
            qs = qs.filter(start_time__gte=now).exclude(
                status__in=["cancelled", "no-show"]
            )

        serializer = ProviderAppointmentSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

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

        patient_identity = updated.patient_identity
        provider_name = ""
        if updated.provider and updated.provider.identity:
            pi = updated.provider.identity
            provider_name = f"Dr. {pi.first_name} {pi.last_name}"

        if patient_identity and new_status != old_status:
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
        serializer = AppointmentCaptureSerializer(captures, many=True)
        return Response(serializer.data)

    def post(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.select_related(
                "provider", "patient_identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data["appointment"] = appointment_id

        serializer = AppointmentCaptureSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        capture = serializer.save(appointment=appointment)

        if appointment.patient_identity:
            refresh_record_summary(appointment.patient_identity, appointment.provider)

        return Response(
            AppointmentCaptureSerializer(capture).data,
            status=status.HTTP_201_CREATED,
        )


class ProviderDashboardStatsView(APIView):
    """
    GET /provider/<identity_id>/dashboard/stats

    Returns field names that exactly match what the frontend components expect:
      MetricsRow  → today_count, this_week_appointments, total_patients_month, avg_duration_minutes
      PendingActions → pending_count
      WeeklyChart    → weekly_data: [{date, day, count}]
    """

    def get(self, request, identity_id):
        try:
            provider = HealthcareProvider.objects.get(identity__id=identity_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        today = now.date()

        # ── Today's appointments ─────────────────────────────────────────────
        today_count = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__date=today,
        ).count()

        # ── This week (Mon → today) ──────────────────────────────────────────
        week_start = today - timedelta(days=today.weekday())  # Monday
        this_week_appointments = ProviderAppointment.objects.filter(
            provider=provider,
            start_time__date__gte=week_start,
            start_time__date__lte=today,
        ).count()

        # ── Total unique patients this calendar month ────────────────────────
        month_start = today.replace(day=1)
        total_patients_month = (
            ProviderAppointment.objects.filter(
                provider=provider,
                start_time__date__gte=month_start,
            )
            .values("patient_email")
            .distinct()
            .count()
        )

        # ── Average consultation duration (completed only) ───────────────────
        completed_qs = ProviderAppointment.objects.filter(
            provider=provider,
            status="completed",
            end_time__isnull=False,
            start_time__isnull=False,
        ).annotate(
            duration=ExpressionWrapper(
                F("end_time") - F("start_time"), output_field=DurationField()
            )
        )
        avg_duration = completed_qs.aggregate(avg=Avg("duration"))["avg"]
        avg_duration_minutes = round(avg_duration.total_seconds() / 60) if avg_duration else 0

        # ── Pending (unconfirmed / scheduled) appointments ───────────────────
        pending_count = ProviderAppointment.objects.filter(
            provider=provider,
            status__in=["scheduled", "pending"],
            start_time__gte=now,
        ).count()

        # ── Weekly data: last 7 days including today ─────────────────────────
        DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekly_data = []
        for i in range(6, -1, -1):          # 6 days ago → today
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
            # MetricsRow fields
            "today_count": today_count,
            "this_week_appointments": this_week_appointments,
            "total_patients_month": total_patients_month,
            "avg_duration_minutes": avg_duration_minutes,
            # PendingActions field
            "pending_count": pending_count,
            # WeeklyChart field
            "weekly_data": weekly_data,
        })
