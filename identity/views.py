from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from django.shortcuts import get_object_or_404
from django.conf import settings

from utils.code_generators import generate_code
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import authenticate, login
from datetime import timedelta
from rest_framework.authentication import TokenAuthentication

from .serializers import IdentitySerializer, HealthcareProviderAccountSerializer
from .models import (
    Identity,
    Otp,
    WorkStationAccount,
    patientAccount,
    FacilityManagerAccount,
    BranchManagerAccount,
    HealthcareProviderAccount,
    AuthCode,
)
import os
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import IntegrityError, DatabaseError
from .utils import generateAuthCode, generateaccessToken, generaterefreshtoken
import jwt
from typing import TypedDict

FRONTEND_URL = os.environ.get("FRONTEND_URL")
ACCOUNT_TYPES = [
    "patient",
    "healthcare_provider",
    "facility_manager",
    "branch_manager",
    "workstation_account",
]


class AccountTypeConfig(TypedDict):
    patient: str
    healthcare_provider: str


ACCOUNT_TYPE_MAP: AccountTypeConfig = {"patient": "patient", "user": ""}


class StatusView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


FROM_EMAIL = settings.EMAIL_HOST_USER


class RegisterView(APIView):
    authentication_classes = [TokenAuthentication]
    queryset = Identity.objects.all()

    def get(self, request, identity_id):
        if not identity_id:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, id=identity_id)
        serializer = IdentitySerializer(identity)
        data = serializer.data

        # Attach insurances from patientAccount — the field lives there,
        # not on Identity, so the serializer won't include it automatically.
        insurances = []
        try:
            account = patientAccount.objects.filter(identity=identity).first()
            if account:
                insurances = account.insurances or []
        except Exception:
            pass
        data["insurances"] = insurances

        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        if not request.data:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        otp = generate_code(length=6, uppercase_only=True)
        print(f"DEBUG OTP for {request.data.get('email')}: {otp}", flush=True)
        message = f"Your email address was used to create an account with veridoctor, use the code {otp} to verify your email address and complete account creation. This code will be valid for the next 10 minutes"
        serializer = IdentitySerializer(data=request.data)
        if serializer.is_valid():
            identity = serializer.save()
            identity_otp = Otp.objects.create(
                code=otp,
                identity_ref=identity,
                send_via="EMAIL",
                purpose="VERIFICATION",
            )
            identity_otp.save()
            import threading
            import requests
            def send_brevo_email():
                requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": os.environ.get("BREVO_API_KEY"), "Content-Type": "application/json"},
                    json={
                        "sender": {"name": "Veridoctor", "email": FROM_EMAIL},
                        "to": [{"email": identity.email}],
                        "subject": "ACCOUNT VERIFICATION",
                        "textContent": message
                    }
                )
            threading.Thread(target=send_brevo_email).start()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, identity_id):
        if not request.data or not identity_id:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, id=identity_id)

        # Save insurances to patientAccount if provided — strip it from the
        # payload first so IdentitySerializer doesn't see an unknown field.
        insurances = request.data.get("insurances", None)
        if insurances is not None:
            try:
                account = patientAccount.objects.filter(identity=identity).first()
                if account:
                    account.insurances = insurances
                    account.save(update_fields=["insurances"])
            except Exception:
                pass

        # Update Identity fields (first_name, last_name, phone_number, gender etc.)
        identity_data = {
            k: v for k, v in request.data.items() if k != "insurances"
        }
        serializer = IdentitySerializer(identity, data=identity_data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return the updated data including insurances
        response_data = serializer.data
        try:
            account = patientAccount.objects.filter(identity=identity).first()
            response_data["insurances"] = account.insurances if account else []
        except Exception:
            response_data["insurances"] = []

        return Response(response_data, status=status.HTTP_200_OK)

    def delete(self, request, identity_id):
        if not identity_id:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, id=identity_id)
        identity.is_active = False
        identity.email_verified = False
        identity.deleted_at = timezone.now()
        identity.save()
        return Response({}, status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not request.data or not email or not password:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = authenticate(request=request, username=email, password=password)
        if identity is not None:
            if identity.email_verified == False:
                return Response(
                    {"user": identity.id, "error": "email not verified"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                code = generateAuthCode(identity)
            except IntegrityError:
                return Response({"error": "an error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except DatabaseError:
                return Response({"error": "an error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            login(request, identity)
            return Response(
                {
                    "user": {
                        "id": identity.id,
                        "first_name": f"{identity.first_name}",
                        "last_name": f"{identity.last_name}",
                    },
                    "detail": "login successfull",
                    "auth_code": code,
                },
                status=status.HTTP_200_OK,
            )
        return Response({"error": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


class TokenView(APIView):
    def post(self, request):
        auth_code = request.GET.get("auth_code")
        identity = request.GET.get("identity")
        if auth_code is None or identity is None:
            return Response({"error": "no code and identity provided"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            temp_auth_code = AuthCode.objects.get(identity__id=identity)
        except Exception:
            return Response({"error": "an error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if temp_auth_code.code != auth_code:
            raise AuthenticationFailed("invalid auth code")
        try:
            jwt.decode(auth_code, settings.JWT_SECRET, algorithms="HS256")
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("expired auth code")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("invalid auth code")

        access_token = generateaccessToken(identity=identity)
        refresh_token = generaterefreshtoken(identity=identity)
        temp_auth_code.delete()
        return Response(
            {"a_token": access_token, "refresh_token": refresh_token},
            status=status.HTTP_200_OK,
        )


class SendOTPView(APIView):
    def post(self, request):
        if not request.data:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = request.data.get("user")
        if not identity:
            return Response({"error": "user required"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, id=identity)
        otp = generate_code(length=6, uppercase_only=True)
        try:
            existing_otp = Otp.objects.get(identity_ref=identity)
            existing_otp.code = otp
            existing_otp.is_used = False
            existing_otp.send_via = "EMAIL"
            existing_otp.purpose = "VERIFICATION"
            existing_otp.created_at = timezone.now()
            existing_otp.save()
        except Otp.DoesNotExist:
            otp_instance = Otp.objects.create(
                code=otp, identity_ref=identity, send_via="EMAIL", purpose="VERIFICATION",
            )
            otp_instance.save()
        try:
            send_mail("TWO FACTOR AUTHENTICATION", f"{otp}", FROM_EMAIL, [identity.email], fail_silently=not settings.DEBUG)
            return Response({"detail": "otp sent to user email"}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"error": "email not sent, retry sending email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyOTPView(APIView):
    def post(self, request):
        otp = request.data.get("otp")
        identity = request.data.get("user")
        if not request.data or not otp or not identity:
            return Response({"error": "bad request, please fill in all required fields"}, status=status.HTTP_400_BAD_REQUEST)
        otp_instance = get_object_or_404(Otp, identity_ref=identity)
        if not otp_instance.code == otp or otp_instance.is_used:
            return Response({"error": "invalid OTP code"}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        if now > (otp_instance.created_at + timedelta(minutes=10)):
            return Response({"error": "OTP expired, request another OTP"}, status=status.HTTP_400_BAD_REQUEST)
        otp_instance.is_used = True
        Identity.objects.filter(id=identity).update(email_verified=True)
        otp_instance.save()
        return Response({"detail": "OTP verified"}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    def post(self, request):
        payload_email = request.data.get("email")
        if not payload_email:
            return Response({"error": "no email provided"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, email=payload_email)
        token = PasswordResetTokenGenerator().make_token(identity)
        signup_url = f"{FRONTEND_URL}/auth/reset-password/{identity.id}/?tkn={token}"
        identity.email_user(
            "PASSWORD RESET REQUEST",
            f"Use the link to reset your password {signup_url}. This link will expire in 10 minutes.",
            FROM_EMAIL,
        )
        return Response({"message": "reset link sent to email"}, status=status.HTTP_200_OK)


class confirmResetPasswordView(APIView):
    def post(self, request):
        token = request.data.get("token")
        new_password = request.data.get("new_password")
        identity_id = request.data.get("identity")
        if not token or not new_password or not identity_id:
            return Response({"error": "invalid credentials provided"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            identity = get_object_or_404(Identity, id=identity_id)
        except Exception:
            return Response({"error": "invalid identity provided"}, status=status.HTTP_400_BAD_REQUEST)
        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user=identity, token=token):
            return Response({"error": "invalid token", "message": "Invalid or malformed password reset link"}, status=status.HTTP_400_BAD_REQUEST)
        identity.set_password(new_password)
        identity.save()
        return Response({"detail": "password reset successful"}, status=status.HTTP_200_OK)


class IdentityAccountsView(APIView):
    def get(self, request, identity_id):
        identity = get_object_or_404(Identity, id=identity_id)
        patient_account = patientAccount.objects.filter(identity__id=identity_id).first()
        facility_manager_account = FacilityManagerAccount.objects.filter(identity__id=identity_id).first()
        branch_manager_account = BranchManagerAccount.objects.filter(identity__id=identity_id).first()
        healthcare_provider_account = HealthcareProviderAccount.objects.filter(identity__id=identity_id).first()

        accounts_data = [
            patient_account and {
                "name": "Patient Account",
                "account_type": ACCOUNT_TYPE_MAP["patient"],
                "id": patient_account.id,
            },
            facility_manager_account and {
                "name": "Facility Manager Account",
                "account_type": "facility_manager",
                "id": facility_manager_account.id,
                "active": facility_manager_account.is_active,
            },
            branch_manager_account and {
                "name": "Branch Manager Account",
                "account_type": "branch_manager",
                "id": branch_manager_account.id,
            },
            healthcare_provider_account and {
                "name": "Healthcare Provider Account",
                "account_type": "healthcare_provider",
                "id": healthcare_provider_account.id,
                "active": healthcare_provider_account.is_active,
            },
        ]

        return Response(
            {
                "identity": {"id": identity.id, "first_name": identity.first_name, "last_name": identity.last_name},
                "accounts": [acc for acc in accounts_data if acc],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, identity_id):
        account_type = request.data.get("account_type")
        if not request.data or not account_type:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        if account_type not in ACCOUNT_TYPES:
            return Response({"error": "invalid account type"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, id=identity_id)
        if account_type == "patient":
            if hasattr(identity, "patientaccount"):
                return Response({"error": "patient account already exists for this identity"}, status=status.HTTP_400_BAD_REQUEST)
            patient_account = patientAccount.objects.create(identity=identity)
            patient_account.save()
            return Response({"detail": "account created"}, status=status.HTTP_201_CREATED)
        elif account_type == "healthcare_provider":
            if hasattr(identity, "healthcareprovideraccount"):
                return Response(
                    {"error": "healthcare provider account already exists for this identity"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            phone_number = request.data.get("phone_number")
            if phone_number:
                identity.phone_number = phone_number
                identity.save()

            provider_payload = request.data.copy()
            provider_payload.pop("phone_number", None)
            provider_payload.pop("account_type", None)

            serializer = HealthcareProviderAccountSerializer(data=provider_payload)
            if serializer.is_valid():
                serializer.save(identity=identity)
                return Response({"detail": "account created"}, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif account_type == "facility_manager":
            if hasattr(identity, "facilitymanageraccount"):
                return Response({"error": "facility manager account already exists for this identity"}, status=status.HTTP_400_BAD_REQUEST)
            facility_account = FacilityManagerAccount.objects.create(identity=identity)
            facility_account.save()
            return Response({"detail": "account created"}, status=status.HTTP_201_CREATED)
        elif account_type == "workstation_account":
            if hasattr(identity, "workstationaccount"):
                return Response({"error": "workstation account already exists for this identity"}, status=status.HTTP_400_BAD_REQUEST)
            workstation_account = WorkStationAccount.objects.create(veri_identifier=identity)
            workstation_account.save()
            return Response({"detail": "account created"}, status=status.HTTP_201_CREATED)
        else:
            return Response({"error": "account type not yet implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)


class ActivateAccountView(APIView):
    def post(self, request, account_type, init_model_id):
        if not request.data or account_type not in ACCOUNT_TYPES:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        pass


class DeactivateAccountView(APIView):
    def post(self, request, identity_id, account_type):
        if account_type not in ACCOUNT_TYPES:
            return Response({"error": "invalid account type"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "account deactivated successfully"}, status=status.HTTP_200_OK)


class DeactivateIdentityView(APIView):
    def post(self, request, identity_id):
        identity = get_object_or_404(Identity, id=identity_id)
        identity.is_active = False
        identity.save()
        return Response({}, status=status.HTTP_204_NO_CONTENT)
