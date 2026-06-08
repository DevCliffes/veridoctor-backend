from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import HealthcareProvider, Service
from .serializers import ServiceSerializer
from identity.models import Identity


class ServiceView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
            services = Service.objects.filter(provider=provider)
            serializer = ServiceSerializer(services, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
            serializer = ServiceSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(provider=provider)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)


class ServiceDetailView(APIView):
    def patch(self, request, identity_id, service_id):
        try:
            service = Service.objects.get(id=service_id)
            serializer = ServiceSerializer(service, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Service.DoesNotExist:
            return Response({"error": "Service not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, identity_id, service_id):
        try:
            service = Service.objects.get(id=service_id)
            service.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Service.DoesNotExist:
            return Response({"error": "Service not found"}, status=status.HTTP_404_NOT_FOUND)
class FormView(APIView):
    def get(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider = HealthcareProvider.objects.get(identity=identity)
            forms = Form.objects.filter(provider=provider)
            serializer = FormSerializer(forms, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except (Identity.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, identity_id):
        try:
            identity = Identity.objects.get(id=identity_id)
            provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
            serializer = FormSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(provider=provider)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Identity.DoesNotExist:
            return Response({"error": "Identity not found"}, status=status.HTTP_404_NOT_FOUND)
