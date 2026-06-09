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
    def get_provider(self, identity_id):
        identity = Identity.objects.get(id=identity_id)
        provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
        return provider

    def get(self, request, identity_id):
        try:
            provider = self.get_provider(identity_id)
            appointments = ProviderAppointment.objects.filter(provider=provider)

            appointment_type = request.query_params.get("appointment_type")
            if appointment_type:
                appointments = appointments.filter(appointment_type=appointment_type)

            filter_value = request.query_params.get("filter")
            now = timezone.now()
            if filter_value == "today":
    appointments = appointments.filter(start_time__date=now.date()).order_by("start_time")
            elif filter_value == "upcoming":
                appointments = appointments.filter(start_time__gte=now)
            elif filter_value == "past":
                appointments = appointments.filter(start_time__lt=now)

            serializer = ProviderAppointmentSerializer(appointments, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, identity_id):
        try:
            provider = self.get_provider(identity_id)
            data = request.data.copy()

            if not data.get("end_time") and data.get("start_time"):
                start_time = parse_datetime(data["start_time"])
                if start_time:
                    if timezone.is_naive(start_time):
                        start_time = timezone.make_aware(start_time)
                    data["end_time"] = (start_time + timedelta(minutes=30)).isoformat()

            serializer = ProviderAppointmentSerializer(data=data)
            if serializer.is_valid():
                serializer.save(provider=provider)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)


class ProviderAppointmentDetailView(APIView):
    def get_appointment(self, identity_id, appointment_id):
        identity = Identity.objects.get(id=identity_id)
        provider = HealthcareProvider.objects.get(identity=identity)
        return ProviderAppointment.objects.get(id=appointment_id, provider=provider)

    def patch(self, request, identity_id, appointment_id):
        try:
            appointment = self.get_appointment(identity_id, appointment_id)
            serializer = ProviderAppointmentSerializer(
                appointment, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, identity_id, appointment_id):
        try:
            appointment = self.get_appointment(identity_id, appointment_id)
            appointment.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)
