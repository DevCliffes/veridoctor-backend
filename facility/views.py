from django.shortcuts import render


from rest_framework import generics
from rest_framework.views import APIView, Response
from .models import Facility
from .serializers import FacilitySerializer
from rest_framework.response import Response
from rest_framework import status


class FacilityView(APIView):
    def get(self, request):
        facilities = Facility.objects.all()
        serializer = FacilitySerializer(facilities, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = FacilitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
