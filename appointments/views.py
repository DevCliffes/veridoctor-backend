from datetime import timedelta
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from identity.models import Identity
from provider.models import HealthcareProvider
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ProviderAppointment
from .serializers import ProviderAppointmentSerializer


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
        elif filter_type == "upcoming":
            appointments = appointments.filter(start_time__gt=now)
        elif filter_type == "past":
            appointments = appointments.filter(start_time__lt=now)

        if appointment_type:
            appointments = appointments.filter(appointment_type=appointment_type)

        appointments = appointments.order_by("start_time")
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


class PatientAppointmentView(APIView):
    def get(self, request):
        patient_email = request.query_params.get("patient_email")
        if not patient_email:
            return Response(
                {"error": "patient_email query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        appointment.status = "cancelled"
        appointment.save()
        serializer = ProviderAppointmentSerializer(appointment)
        return Response(serializer.data)
