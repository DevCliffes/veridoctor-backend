from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import HealthcareProvider, Service
from .serializers import ServiceSerializer
from identity.models import Identity


class ServiceView(APIView):
    def get(self, request, provider_id):
        """Get all services for a provider"""
        try:
            provider = HealthcareProvider.objects.get(id=provider_id)
            services = Service.objects.filter(provider=provider)
            serializer = ServiceSerializer(services, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, provider_id):
        """Add a new service for a provider"""
        try:
            provider = HealthcareProvider.objects.get(id=provider_id)
            serializer = ServiceSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(provider=provider)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
