from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from identity.models import Identity
from provider.models import HealthcareProvider
from .models import PatientProviderRecordSummary
from .serializers import PatientProviderRecordSummarySerializer


class PatientRecordSummaryView(APIView):
    """
    Returns the cross-provider record summary for a patient — what other
    providers have records for them, with counts and recency only, never
    clinical content. Excludes the requesting provider's own summary,
    since they already have full access to their own records.
    """

    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        exclude_provider_identity_id = request.query_params.get("exclude_provider")
        summaries = PatientProviderRecordSummary.objects.filter(
            patient_identity=patient_identity
        ).select_related("provider", "provider__identity")

        if exclude_provider_identity_id:
            try:
                exclude_provider = HealthcareProvider.objects.get(
                    identity__id=exclude_provider_identity_id
                )
                summaries = summaries.exclude(provider=exclude_provider)
            except HealthcareProvider.DoesNotExist:
                pass

        serializer = PatientProviderRecordSummarySerializer(summaries, many=True)
        return Response(serializer.data)
