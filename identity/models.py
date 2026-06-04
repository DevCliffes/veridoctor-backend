"""Contains identifier and account information for application users"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from .managers import CustomUserManager
from shared.models import BaseModel


class AuthCode(models.Model):
    """an auth code to be used for auth token generation"""

    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    code = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)


class Identity(AbstractUser):
    """
    Used to identify a user in the application
    """

    GENDER_CHOICES = [
        ("MALE", "male"),
        ("FEMALE", "female"),
        ("OTHER", "other"),
        ("UNKNOWN", "unknown"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    gender = models.CharField(
        max_length=20, choices=GENDER_CHOICES, null=True, blank=True
    )
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=30, null=True, blank=True, unique=True)
    email_verified = models.BooleanField(default=False)
    phone_number_verified = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    username = None

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]


class Otp(BaseModel):
    """
    One time password model for the identity service
    """

    SEND_VIA_CHOICES = [("SMS", "sms"), ("EMAIL", "email")]

    OTP_PURPOSE = [("VERIFICATION", "verification"), ("PASSRESET", "passreset")]

    code = models.CharField(max_length=6)
    identity_ref = models.OneToOneField(Identity, on_delete=models.CASCADE)
    send_via = models.CharField(max_length=10, choices=SEND_VIA_CHOICES)
    purpose = models.CharField(max_length=20, choices=OTP_PURPOSE)
    is_used = models.BooleanField(default=False)


class ProviderQualificationsModel(BaseModel):
    """
    Holds the qualifications of a healthcare provider
    """

    qualification_name = models.CharField(max_length=255)
    institution_name = models.CharField(max_length=255)
    year_obtained = models.IntegerField()


class HealthcareProviderAccount(BaseModel):
    """
    A healthcare provider account
    """

    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    licence_number = models.CharField(max_length=255, unique=True)
    licence_type = models.CharField(max_length=255)
    practice_type = models.CharField(max_length=255)
    speciality = models.CharField(max_length=255, null=True, blank=True)
    sub_speciality = models.CharField(max_length=255, null=True, blank=True)
    qualifications = models.ManyToManyField(
        "identity.ProviderQualificationsModel", blank=True
    )
    is_verified = models.BooleanField(default=False)
    verified_on = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)


class patientAccount(BaseModel):
    """
    Patient account
    """

    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)


class FacilityManagerAccount(BaseModel):
    """
    A facility manager account
    """

    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.identity.first_name} {self.identity.last_name}"


# TODO: remove this file and replace all instances in the facility manger account
class BranchManagerAccount(BaseModel):
    """
    A facility branch manager account
    """

    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.identity.first_name} {self.identity.last_name} - {self.identity.email}"


class WorkStationAccount(BaseModel):
    """
    A workstation account for a user
    """

    veri_identifier = models.OneToOneField(
        "identity.Identity", on_delete=models.CASCADE
    )
    workstations = models.ManyToManyField(
        "facility.Workstation", blank=True, related_name="workstations"
    )
