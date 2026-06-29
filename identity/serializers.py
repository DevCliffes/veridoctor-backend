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
    "deleted_at",
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
        user = self.Meta.model.objects.create_user(
            email=email, password=password, **validated_data
        )
        return user

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop("password")
        representation.pop("is_active")
        representation.pop("phone_number_verified")
        representation.pop("email_verified")
        representation.pop("deleted_at")
        representation.pop("last_login")
        representation.pop("is_superuser")
        representation.pop("is_staff")
        representation.pop("date_joined")
        return representation

    def update(self, instance, validated_data):
        # Password and email are intentionally excluded from generic
        # profile updates:
        # - Password changes must go through the OTP/token-verified
        #   reset-password flow (ResetPasswordView / confirmResetPasswordView).
        #   Applying it here via plain setattr() would store it unhashed,
        #   since the base update() does not call set_password().
        # - Email is the USERNAME_FIELD / login identifier, so changing it
        #   needs its own re-verification flow, not a silent profile edit.
        validated_data.pop("password", None)
        validated_data.pop("email", None)
        return super().update(instance, validated_data)


class HealthcareProviderAccountSerializer(ModelSerializer):
    """
    Serializer for the HealthcareProviderAccount model.
    subspecialties is a JSONField (list of strings) — readable and writable
    by any view that uses this serializer.
    """

    class Meta:
        model = HealthcareProviderAccount
        fields = "__all__"
        read_only_fields = ["id", "identity", "created_at", "updated_at"]
