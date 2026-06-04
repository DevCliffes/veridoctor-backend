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
    """
    A simple view to return the status of the identity service
    """

    def get(self, request):
        return Response({"status": "ok"})


FROM_EMAIL = settings.EMAIL_HOST_USER


class RegisterView(APIView):
    """
    Register a new identity to the system
    """

    authentication_classes = [TokenAuthentication]
    queryset = Identity.objects.all()

    def post(self, request):
        """creates a new identity on the system"""
        if not request.data:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        otp = generate_code(length=6, uppercase_only=True)
        message = f"Your email address was used to create an account with veridoctor, use the code {otp} to verify your email address and complete account creation. This code will be valid for the next 10 minutes"  # TODO: use a template for messages
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
            identity.email_user("ACCOUNT VERIFICATION", message, FROM_EMAIL)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, identity_id):
        """updates an existing identity"""
        if not request.data or not identity_id:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        identity = get_object_or_404(Identity, id=identity_id)
        serializer = IdentitySerializer(identity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, identity_id):
        """soft deletes an identity"""
        if not identity_id:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        # confirm that the deleting user has sufficient permissions before proceeding with this action
        # soft delete the IDentity model instead of entirely deleting it
        identity = get_object_or_404(Identity, id=identity_id)
        identity.is_active = False
        identity.email_verified = False
        identity.deleted_at = timezone.now()
        return Response({}, status=status.HTTP_204_NO_CONTENT)


# TODO: change the login view here and use tokens insted. set a httponly cookie to the request to ensure token security
class LoginView(APIView):
    """handles idenitty login to the platform"""

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not request.data or not email or not password:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        identity = authenticate(request=request, username=email, password=password)
        if identity is not None:
            if identity.email_verified == False:
                return Response(
                    {"user": identity.id, "error": "email not verified"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                code = generateAuthCode(identity)
            # TODO: find a better error message dor these errors
            except IntegrityError:
                return Response(
                    {"error": "an error occurred"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            except DatabaseError:
                return Response(
                    {"error": "an error occurred"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

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

        return Response(
            {"error": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
        )


class TokenView(APIView):
    def post(self, request):
        """generates a token for the user"""
        auth_code = request.GET.get("auth_code")
        identity = request.GET.get("identity")
        if auth_code is None or identity is None:
            return Response(
                {"error": "no code and identity provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            temp_auth_code = AuthCode.objects.get(identity=identity)
        # TODO: catch the validation error thrown for invalid uuids and error accordingly
        # catch invalid uuids being provided
        except Exception:
            return Response(
                {"error": "an error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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
        # get the code from the params and use it to generate a new access token
        return Response(
            {"a_token": access_token, "refresh_token": refresh_token},
            status=status.HTTP_200_OK,
        )


class SendOTPView(APIView):
    """Resends an OTP"""

    def post(self, request):
        if not request.data:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        identity = request.data.get("user")
        if not identity:
            return Response(
                {"error": "user required"}, status=status.HTTP_400_BAD_REQUEST
            )
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
                code=otp,
                identity_ref=identity,
                send_via="EMAIL",
                purpose="VERIFICATION",
            )
            otp_instance.save()
        try:
            send_mail(
                "TWO FACTOR AUTHENTICATION",
                f"{otp}",
                FROM_EMAIL,
                [identity.email],
                fail_silently=not settings.DEBUG,
            )
            return Response(
                {"detail": "otp sent to user email"}, status=status.HTTP_200_OK
            )
        except Exception as e:
            # TODO: configure rabbitmq to retry sending emails that have not been sent
            return Response(
                {"error": "email not sent, retry sending email"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyOTPView(APIView):
    """class to verify an OTP"""

    def post(self, request):
        otp = request.data.get("otp")
        identity = request.data.get("user")
        if not request.data or not otp or not identity:
            return Response(
                {"error": "bad request, please fill in all required fields"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        otp_instance = get_object_or_404(Otp, identity_ref=identity)
        if not otp_instance.code == otp or otp_instance.is_used:
            return Response(
                {"error": "invalid OTP code"}, status=status.HTTP_400_BAD_REQUEST
            )
        now = timezone.now()
        if now > (otp_instance.created_at + timedelta(minutes=10)):
            return Response(
                {"error": "OTP expired, request another OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        otp_instance.is_used = True
        Identity.objects.filter(id=identity).update(email_verified=True)
        otp_instance.save()
        return Response({"detail": "OTP verified"}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    """
    Handles password reset for identities
    """

    def post(self, request):
        payload_email = request.data.get("email")
        if not payload_email:
            return Response(
                {"error": "no email provided"}, status=status.HTTP_400_BAD_REQUEST
            )
        identity = get_object_or_404(Identity, email=payload_email)
        token = PasswordResetTokenGenerator().make_token(identity)
        signup_url = f"{FRONTEND_URL}/auth/reset-password/{identity.id}/?tkn={token}"
        identity.email_user(
            "PASSWORD RESET REQUEST",
            f"Use the link to reset your password {signup_url}. This link will expire in 10 minutes.",
            FROM_EMAIL,
        ) 
        return Response(
            {"message": "reset link sent to email"}, status=status.HTTP_200_OK
        )


class confirmResetPasswordView(APIView):
    """
    Confirms password reset for identities
    """

    def post(self, request):
        # change the token to be in the url param
        token = request.data.get("token")
        new_password = request.data.get("new_password")
        identity_id = request.data.get("identity")

        if not token or not new_password or not identity_id:
            return Response(
                {
                    "error": "invalid credentials provided",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            identity = get_object_or_404(Identity, id=identity_id)
        except Exception:
            return Response(
                {"error": "invalid identity provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user=identity, token=token):
            return Response(
                {
                    "error": "invalid token",
                    "message": "Invalid or malformed password reset link",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        identity.set_password(new_password)
        identity.save()
        # TODO: add background text to send email to user telling them about  a password reset
        return Response(
            {"detail": "password reset successful"}, status=status.HTTP_200_OK
        )


class IdentityAccountsView(APIView):
    """
    Handles identity accounts CRUD operations
    """

    def get(self, request, identity_id):
        """Fetches all accounts associated with an identity"""
        # TODO: find a better way to show and get the accounts associated with a specific identity
        identity = get_object_or_404(Identity, id=identity_id)
        patient_account = patientAccount.objects.filter(
            identity__id=identity_id
        ).first()
        facility_manager_account = FacilityManagerAccount.objects.filter(
            identity__id=identity_id
        ).first()
        branch_manager_account = BranchManagerAccount.objects.filter(
            identity__id=identity_id
        ).first()
        healthcare_provider_account = HealthcareProviderAccount.objects.filter(
            identity__id=identity_id
        ).first()

        accounts_data = [
            patient_account
            and {
                "name": "Patient Account",
                "account_type": ACCOUNT_TYPE_MAP["patient"],
                "id": patient_account.id,
            },
            facility_manager_account
            and {
                "name": "Facility Manager Account",
                "account_type": "facility_manager",
                "id": facility_manager_account.id,
                "active": facility_manager_account.is_active,
            },
            branch_manager_account
            and {
                "name": "Branch Manager Account",
                "account_type": "branch_manager",
                "id": branch_manager_account.id,
            },
            healthcare_provider_account
            and {
                "name": "Healthcare Provider Account",
                "account_type": "healthcare_provider",
                "id": healthcare_provider_account.id,
                "active": healthcare_provider_account.is_active,
            },
        ]

        return Response(
            {
                "identity": {
                    "id": identity.id,
                    "first_name": identity.first_name,
                    "last_name": identity.last_name,
                },
                "accounts": [acc for acc in accounts_data if acc],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, identity_id):
        """Handles creation of a patient account"""
        account_type = request.data.get("account_type")
        if not request.data or not account_type:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        if account_type not in ACCOUNT_TYPES:
            return Response(
                {"error": "invalid account type"}, status=status.HTTP_400_BAD_REQUEST
            )
        identity = get_object_or_404(Identity, id=identity_id)
        # patient account creation
        if account_type == "patient":
            # creates patient account directly because it only requires an identity reference
            # check if the identity already has a patient account
            if hasattr(identity, "patientaccount"):
                return Response(
                    {"error": "patient account already exists for this identity"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            patient_account = patientAccount.objects.create(identity=identity)
            patient_account.save()
            return Response(
                {"detail": "account created"}, status=status.HTTP_201_CREATED
            )
        elif account_type == "healthcare_provider":
            # implement healthcare provider account creation here
            if hasattr(identity, "healthcareprovideraccount"):
                return Response(
                    {
                        "error": "healthcare provider account already exists for this identity"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # TODO: pop phone number from the request data
            phone_number = request.data.get("phone_number")

            if phone_number:
                identity.phone_number = phone_number
                identity.save()
            provider_account = HealthcareProviderAccount.objects.create(
                identity=identity,
            )
            provider_account.save()
            serializer = HealthcareProviderAccountSerializer(
                provider_account, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
            return Response(
                {"detail": "account created"},
                status=status.HTTP_201_CREATED,
            )
        elif account_type == "facility_manager":
            # implement healthcare provider account creation here
            facility_account = FacilityManagerAccount.objects.create()
            facility_account.save()
            if hasattr(identity, "facilitymanageraccount"):
                return Response(
                    {"detail": "account created"},
                    status=status.HTTP_201_CREATED,
                )
            return Response(
                {"error": "account type not yet implemented"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        elif account_type == "workstation_account":
            workstation_account = WorkStationAccount.objects.create()
            workstation_account.save()
            if hasattr(identity, "workstationaccount"):
                return Response(
                    {"detail": "account created"},
                    status=status.HTTP_201_CREATED,
                )
            return Response(
                {"error": "account type not yet implemented"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        else:
            return Response(
                {"error": "account type not yet implemented"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )


class ActivateAccountView(APIView):
    """
    Handles account activations for users that need extra authorization. Healthcare providers, facilities e.t.c
    """

    def post(self, request, account_type, init_model_id):
        """
        Activates an account that has an init model
        """
        if not request.data or account_type not in ACCOUNT_TYPES:
            return Response(
                {"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST
            )
        # get the init model using the provided init_id and use the data therein to activate an account
        pass


class DeactivateAccountView(APIView):
    """
    Deactivates an account type ensuring the user cannot access the account information
    """

    def post(self, request, identity_id, account_type):
        # ensure only admins can perform this action
        # ensure that only authorized identities can deactivate an account check for specific headers in the request to ensure that the action is valid and the user does not deactivate accounts that they do not have jurisdiction over
        # get the account by account-id and the account type and use them to dectivae the account
        if account_type not in ACCOUNT_TYPES:
            return Response(
                {"error": "invalid account type"}, status=status.HTTP_400_BAD_REQUEST
            )
        # get account for the specific user and deactivate it
        return Response(
            {"message": "account deactivated successfully"}, status=status.HTTP_200_OK
        )


class DeactivateIdentityView(APIView):
    """
    Handles account deactivations in the platform
    deactivaed identities cannot access the platform whatsoever
    """

    def post(self, request, identity_id):
        # Ensure only admins can deactivate identities
        identity = get_object_or_404(Identity, id=identity_id)
        identity.is_active = False
        identity.save()
        return Response({}, status=status.HTTP_204_NO_CONTENT)
