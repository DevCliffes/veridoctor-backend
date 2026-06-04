from rest_framework.serializers import ModelSerializer

from .models import Facility


class FacilitySerializer(ModelSerializer):
    """
    serilaizer for the facility model
    """

    class Meta:
        model = Facility
        fields = "__all__"
