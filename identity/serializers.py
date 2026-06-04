from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer

from .models import Identity, HealthcareProviderAccount

IDENTITY_PROTECTED_FIELDS = [
    "is_active",
    "email_verified",
    "phone_number_verified",
    "deleted_at",
    "id", 
    "last_login",
    "date_joined",
    "is_staff",
    "is_superuser",
    "created_at",
    "deleted_at"
]

class IdentitySerializer(ModelSerializer):
    """
    serializer class for the Identity model
    """

    class Meta:
        model = Identity
        exclude = ["user_permissions", "groups"]
        read_only_fields = IDENTITY_PROTECTED_FIELDS

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        email = validated_data.pop("email", None)
        user = self.Meta.model.objects.create_user(email=email,password=password,**validated_data)
        return user

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop("password")
        representation.pop("is_active")
        representation.pop("phone_number_verified")
        representation.pop("email_verified")
        representation.pop("deleted_at")
        representation.pop('last_login')
        representation.pop('is_superuser')
        representation.pop('is_staff')
        representation.pop('date_joined')
        # remove other fields from the get requests here
        return representation

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)

class HealthcareProviderAccountSerializer(ModelSerializer):
    '''
    Serializer for the HealthcareProviderAccount model
    '''
    class Meta:
        model = HealthcareProviderAccount
        fields = "__all__"
        read_only_fields = ["id", "identity", "created_at", "updated_at"]