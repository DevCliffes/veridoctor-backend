from django.contrib.auth.hashers import make_password, check_password
from django.db import models
from django.utils import timezone
from identity.models import Identity
from shared.models import BaseModel

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class PatientRecordsPin(BaseModel):
    """
    Patient-side PIN gating access to their own health records.
    Independent of platform login credentials (JWT).
    """
    patient_identity = models.OneToOneField(
        Identity, on_delete=models.CASCADE, related_name="records_pin"
    )
    pin_hash = models.CharField(max_length=128)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)
        self.failed_attempts = 0
        self.locked_until = None

    def check_pin(self, raw_pin):
        return check_password(raw_pin, self.pin_hash)

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failure(self):
        self.failed_attempts += 1
        if self.failed_attempts >= MAX_FAILED_ATTEMPTS:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=LOCKOUT_MINUTES)
        self.save(update_fields=["failed_attempts", "locked_until", "updated_at"])

    def register_success(self):
        self.failed_attempts = 0
        self.locked_until = None
        self.save(update_fields=["failed_attempts", "locked_until", "updated_at"])

    def __str__(self):
        return f"RecordsPin({self.patient_identity})"
