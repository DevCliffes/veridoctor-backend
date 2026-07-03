from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .pin_models import PatientRecordsPin, MAX_FAILED_ATTEMPTS
from .pin_permissions import generate_unlock_token


def _is_valid_pin_format(pin):
    return bool(pin) and pin.isdigit() and 4 <= len(pin) <= 8


class RecordsPinStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        has_pin = PatientRecordsPin.objects.filter(patient_identity=request.user).exists()
        return Response({"has_pin": has_pin})


class RecordsPinSetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        pin = request.data.get("pin")
        if not _is_valid_pin_format(pin):
            return Response({"error": "pin must be 4-8 digits"}, status=status.HTTP_400_BAD_REQUEST)

        if PatientRecordsPin.objects.filter(patient_identity=request.user).exists():
            return Response(
                {"error": "PIN already set. Use change or reset instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pin_obj = PatientRecordsPin(patient_identity=request.user)
        pin_obj.set_pin(pin)
        pin_obj.save()

        return Response({"detail": "PIN set successfully."}, status=status.HTTP_201_CREATED)


class RecordsPinVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        pin = request.data.get("pin")
        if not pin:
            return Response({"error": "pin is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pin_obj = PatientRecordsPin.objects.get(patient_identity=request.user)
        except PatientRecordsPin.DoesNotExist:
            return Response({"error": "No PIN set for this account."}, status=status.HTTP_400_BAD_REQUEST)

        if pin_obj.is_locked():
            return Response(
                {"error": "Too many failed attempts. Try again later.", "locked_until": pin_obj.locked_until},
                status=status.HTTP_423_LOCKED,
            )

        if not pin_obj.check_pin(pin):
            pin_obj.register_failure()
            remaining = max(0, MAX_FAILED_ATTEMPTS - pin_obj.failed_attempts)
            return Response(
                {"error": "Incorrect PIN.", "remaining_attempts": remaining},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pin_obj.register_success()
        token = generate_unlock_token(request.user.id)
        return Response({"unlock_token": token, "expires_in": 900})


class RecordsPinChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_pin = request.data.get("current_pin")
        new_pin = request.data.get("new_pin")

        if not current_pin or not _is_valid_pin_format(new_pin):
            return Response(
                {"error": "current_pin and a valid 4-8 digit new_pin are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pin_obj = PatientRecordsPin.objects.get(patient_identity=request.user)
        except PatientRecordsPin.DoesNotExist:
            return Response({"error": "No PIN set for this account."}, status=status.HTTP_400_BAD_REQUEST)

        if pin_obj.is_locked():
            return Response({"error": "Too many failed attempts. Try again later."}, status=status.HTTP_423_LOCKED)

        if not pin_obj.check_pin(current_pin):
            pin_obj.register_failure()
            return Response({"error": "Current PIN is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        pin_obj.set_pin(new_pin)
        pin_obj.save()
        return Response({"detail": "PIN updated successfully."})


# RecordsPinResetView intentionally omitted — needs to know whether patient
# re-auth uses OTP or password before this can be written correctly.
class RecordsPinResetView(APIView):
    """
    Forgot-PIN flow: patient re-authenticates with their account password,
    then sets a new PIN. Identity extends AbstractUser, so check_password
    is available natively.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        password = request.data.get("password")
        new_pin = request.data.get("new_pin")

        if not password:
            return Response({"error": "password is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not _is_valid_pin_format(new_pin):
            return Response({"error": "new_pin must be 4-8 digits"}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_password(password):
            return Response({"error": "Password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        pin_obj, _ = PatientRecordsPin.objects.get_or_create(patient_identity=request.user)
        pin_obj.set_pin(new_pin)
        pin_obj.save()

        return Response({"detail": "PIN reset successfully."})
