"""Contains identifier and account information for application users"""

import uuid
import random
import string

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
    """Used to identify a user in the application"""
    GENDER_CHOICES = [
        ("MALE", "male"),
        ("FEMALE", "female"),
        ("OTHER", "other"),
        ("UNKNOWN", "unknown"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, null=True, blank=True)
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
    """One time password model for the identity service"""
    SEND_VIA_CHOICES = [("SMS", "sms"), ("EMAIL", "email")]
    OTP_PURPOSE = [("VERIFICATION", "verification"), ("PASSRESET", "passreset")]

    code = models.CharField(max_length=6)
    identity_ref = models.OneToOneField(Identity, on_delete=models.CASCADE)
    send_via = models.CharField(max_length=10, choices=SEND_VIA_CHOICES)
    purpose = models.CharField(max_length=20, choices=OTP_PURPOSE)
    is_used = models.BooleanField(default=False)


class ProviderQualificationsModel(BaseModel):
    """Holds the qualifications of a healthcare provider"""
    qualification_name = models.CharField(max_length=255)
    institution_name = models.CharField(max_length=255)
    year_obtained = models.IntegerField()


class HealthcareProviderAccount(BaseModel):
    """A healthcare provider account"""
    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    licence_number = models.CharField(max_length=255, unique=True, null=True, blank=True)
    licence_type = models.CharField(max_length=255, blank=True, default="")
    practice_type = models.CharField(max_length=255, blank=True, default="")
    speciality = models.CharField(max_length=255, null=True, blank=True)
    sub_speciality = models.CharField(max_length=255, null=True, blank=True)
    subspecialties = models.JSONField(
        default=list,
        blank=True,
        help_text="List of subspecialty strings e.g. ['Pediatric Cardiology', 'Sports Medicine']",
    )
    qualifications = models.ManyToManyField(
        "identity.ProviderQualificationsModel", blank=True
    )
    is_verified = models.BooleanField(default=False)
    verified_on = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)


class patientAccount(BaseModel):
    """Patient account"""
    BLOOD_TYPE_CHOICES = [
        ("A+", "A+"), ("A-", "A-"),
        ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"),
        ("O+", "O+"), ("O-", "O-"),
        ("UNKNOWN", "Unknown"),
    ]

    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    patient_uid = models.CharField(max_length=20, unique=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    blood_type = models.CharField(
        max_length=10, choices=BLOOD_TYPE_CHOICES, blank=True, default="UNKNOWN"
    )
    allergies = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allergy strings e.g. ['Penicillin', 'Latex']",
    )
    insurances = models.JSONField(
        default=list,
        blank=True,
        help_text="Insurance providers the patient is covered under e.g. ['NHIF', 'AAR']",
    )

    def save(self, *args, **kwargs):
        if not self.patient_uid:
            while True:
                uid = "VD-" + "".join(random.choices(string.digits, k=5))
                if not patientAccount.objects.filter(patient_uid=uid).exists():
                    self.patient_uid = uid
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.identity.first_name} {self.identity.last_name} ({self.patient_uid})"


class FacilityManagerAccount(BaseModel):
    """A facility manager account"""
    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.identity.first_name} {self.identity.last_name}"


class BranchManagerAccount(BaseModel):
    """A facility branch manager account"""
    identity = models.OneToOneField("identity.Identity", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.identity.first_name} {self.identity.last_name} - {self.identity.email}"


class WorkStationAccount(BaseModel):
    """A workstation account for a user"""
    veri_identifier = models.OneToOneField(
        "identity.Identity", on_delete=models.CASCADE
    )
    workstations = models.ManyToManyField(
        "facility.Workstation", blank=True, related_name="workstations"
    )
