from django.utils import timezone
from django.db.models import Avg, F, ExpressionWrapper, DurationField, Count
from identity.models import Identity
from provider.models import HealthcareProvider
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from datetime import timedelta

from .models import AppointmentCapture, ProviderAppointment
from .serializers import AppointmentCaptureSerializer, ProviderAppointmentSerializer


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
            appointments = appointments.filter(start_time__date=now.date())
            appointments = appointments.order_by("start_time")
        elif filter_type == "upcoming":
            appointments = appointments.filter(start_time__gt=now)
            appointments = appointments.order_by("start_time")
        elif filter_type == "past":
            appointments = appointments.filter(start_time__lt=now)
            appointments = appointments.order_by("-start_time")  # newest first
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

        serializer = ProviderAppointmentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(provider=provider)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProviderAppointmentDetailView(APIView):
    def get(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProviderAppointmentSerializer(appointment)
        return Response(serializer.data)

    def patch(self, request, identity_id, appointment_id):
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProviderAppointmentSerializer(appointment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
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

        serializer = AppointmentCaptureSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(appointment=appointment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProviderDashboardStatsView(APIView):
    """Returns stats for the dashboard: this_week, total_patients_month, avg_duration_month, weekly_counts."""
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()

        # This week (Mon–Sun)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        # This month
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_qs = ProviderAppointment.objects.filter(provider=provider)

        # This week counts
        week_qs = base_qs.filter(start_time__gte=week_start, start_time__lt=week_end)
        this_week_appointments = week_qs.count()
        this_week_patients = week_qs.values("patient_email").distinct().count()

        # Monthly distinct patients
        month_qs = base_qs.filter(start_time__gte=month_start)
        total_patients_month = month_qs.values("patient_email").distinct().count()

        # Average duration (minutes) this month
        month_with_duration = month_qs.annotate(
            duration=ExpressionWrapper(
                F("end_time") - F("start_time"), output_field=DurationField()
            )
        )
        avg_duration_td = month_with_duration.aggregate(avg=Avg("duration"))["avg"]
        avg_duration_minutes = int(avg_duration_td.total_seconds() / 60) if avg_duration_td else 0

        # Weekly chart data — last 7 days, count per day
        weekly_data = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            count = base_qs.filter(start_time__date=day).count()
            weekly_data.append({
                "date": day.isoformat(),
                "day": day.strftime("%a"),
                "count": count,
            })

        return Response({
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
        filter_type = request.query_params.get("filter", "upcoming")

        if filter_type == "today":
            appointments = appointments.filter(start_time__date=now.date())
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
        serializer = ProviderAppointmentSerializer(appointment)
        return Response(serializer.data)
