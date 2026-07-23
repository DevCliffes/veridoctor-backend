from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import AuthenticationFailed
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.cache import cache

from utils.code_generators import generate_code
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import authenticate, login
from datetime import timedelta

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
from .emails import send_otp_email
import os
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import IntegrityError, DatabaseError
from .utils import generateAuthCode, generateaccessToken, generaterefreshtoken
import jwt
from typing import TypedDict
import threading

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


def _identity_authorised(request, identity_id):
    """
    Shared ownership check used by views that can legitimately be called
    in TWO different auth states:

      1. Fully authenticated -- request.user is a real, logged-in
         Identity (normal JWTAuthentication via Authorization header),
         checked against identity_id as usual.

      2. Pre-session -- called from the login handoff page
         (apps/web /auth/accounts/{id}) BEFORE any access token exists.
         At this point all the caller has is the one-time auth_code
         LoginView just issued, passed as ?auth_tkn=. We validate it
         against the AuthCode row exactly like TokenView does, but
         WITHOUT deleting it -- TokenView is still the thing that
         consumes it later, once the user picks an account and the
         chosen app (provider/health-portal) does its own real token
         exchange via /identity/authorise. Consuming it here would
         break that later exchange.

    Returns True/False rather than raising, so callers can return their
    own 403 response shape.
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        if str(user.id) == str(identity_id):
            return True

    auth_tkn = request.query_params.get("auth_tkn")
    if not auth_tkn:
        return False

    try:
        temp_auth_code = AuthCode.objects.get(identity__id=identity_id)
    except AuthCode.DoesNotExist:
        return False

    if temp_auth_code.code != auth_tkn:
        return False

    try:
        jwt.decode(auth_tkn, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False

    return True


def _cache_incr(key, timeout):
    """
    Increment a counter that may not exist yet, in a race-safe-enough way
    for a single Postgres-backed cache table (DatabaseCache does the
    increment as an UPDATE, so concurrent requests don't just clobber
    each other's writes the way plain get/set would).

    cache.add() sets the key ONLY if absent, seeding it at 1 with the
    given timeout. If it already existed, cache.incr() bumps it without
    touching its existing TTL -- exactly what a fixed rolling window
    needs (the window started when the key was first seeded, not on
    every subsequent request).
    """
    added = cache.add(key, 1, timeout)
    if added:
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # Key expired between add() and incr() (razor-thin race) -- reset it.
        cache.set(key, 1, timeout)
        return 1


class RegisterView(APIView):
    """
    GET/PATCH/DELETE act on an existing identity and require the caller
    to BE that identity. POST is signup and must stay public.

    FIX: this class previously declared
    `authentication_classes = [TokenAuthentication]` -- DRF's built-in
    TokenAuthentication, a completely different mechanism from
    identity.authentication.JWTAuthentication, which every other view in
    this project relies on via the global DEFAULT_AUTHENTICATION_CLASSES
    setting and which nothing in this codebase actually issues tokens
    for (no Token.objects.create anywhere, no Authorization: Token
    <key> usage). Declaring it here silently overrode the global JWT
    auth for this view only, meaning request.user would likely never
    populate correctly even with IsAuthenticated added. Removed so this
    view uses the same JWT auth as everywhere else.

    CONFIRMED SAFE TO DEPLOY: verified no Token.objects.create anywhere
    in the codebase, rest_framework.authtoken isn't an installed app,
    and a comment in identity/authentication.py already documents that
    this project issues its own JWTs instead of DRF's token model.
    """
    queryset = Identity.objects.all()

    def get_permissions(self):
        if self.request.method == "POST":
            return []
        return [IsAuthenticated()]

    def get(self, request, identity_id):
        if not identity_id:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)

        # FIX: previously no permission check at all -- any caller could
        # read any identity's full profile (name, email, phone, gender,
        # insurances) just by knowing identity_id.
        if str(request.user.id) != str(identity_id):
            return Response(
                {"error": "You do not have permission to view this profile"},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        email = request.data.get("email")

        # FIX: previously any duplicate email — verified or not — hit
        # IdentitySerializer's UniqueValidator and dead-ended the signup
        # form with a raw "already exists" error, even for someone who'd
        # started signup before, never got/used the OTP, and was simply
        # trying again. We now distinguish the two cases explicitly:
        #   - email belongs to an already-verified account -> real
        #     duplicate, keep the exact same error shape as before so
        #     nothing downstream (frontend error parsing) breaks.
        #   - email belongs to an unverified account -> treat this as
        #     "resume verification", not a new registration: issue a
        #     fresh OTP against the existing identity and hand the
        #     frontend enough to redirect straight to the OTP screen.
        if email:
            existing = Identity.objects.filter(email=email).first()
            if existing:
                if existing.email_verified:
                    return Response(
                        {"email": ["user with this email already exists"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                otp = generate_code(length=6, digits_only=True)
                print(f"DEBUG OTP resend for unverified {email}: {otp}", flush=True)
                Otp.objects.update_or_create(
                    identity_ref=existing,
                    defaults={
                        "code": otp,
                        "is_used": False,
                        "send_via": "EMAIL",
                        "purpose": "VERIFICATION",
                        "created_at": timezone.now(),
                    },
                )

                # Sent via Resend now instead of Brevo — send_otp_email()
                # builds its own subject/HTML body from the code, so the
                # old plaintext `message` string is no longer used here.
                threading.Thread(
                    target=send_otp_email, args=(existing.email, otp)
                ).start()

                return Response(
                    {"id": str(existing.id), "requires_verification": True},
                    status=status.HTTP_200_OK,
                )

        otp = generate_code(length=6, digits_only=True)
        print(f"DEBUG OTP for {request.data.get('email')}: {otp}", flush=True)
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

            # Sent via Resend now instead of Brevo.
            threading.Thread(
                target=send_otp_email, args=(identity.email, otp)
            ).start()

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, identity_id):
        if not request.data or not identity_id:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)

        # FIX: previously anyone could update any identity's profile
        # fields (including insurances) just by knowing identity_id.
        if str(request.user.id) != str(identity_id):
            return Response(
                {"error": "You do not have permission to modify this profile"},
                status=status.HTTP_403_FORBIDDEN,
            )

        identity = get_object_or_404(Identity, id=identity_id)

        insurances = request.data.get("insurances", None)
        if insurances is not None:
            try:
                account = patientAccount.objects.filter(identity=identity).first()
                if account:
                    account.insurances = insurances
                    account.save(update_fields=["insurances"])
            except Exception:
                pass

        identity_data = {
            k: v for k, v in request.data.items() if k != "insurances"
        }
        serializer = IdentitySerializer(identity, data=identity_data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

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

        # FIX: previously anyone could deactivate any account just by
        # knowing identity_id -- an unauthenticated way to lock any user
        # out of their own account.
        if str(request.user.id) != str(identity_id):
            return Response(
                {"error": "You do not have permission to deactivate this account"},
                status=status.HTTP_403_FORBIDDEN,
            )

        identity = get_object_or_404(Identity, id=identity_id)
        identity.is_active = False
        identity.email_verified = False
        identity.deleted_at = timezone.now()
        identity.save()
        return Response({}, status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    # FIX: explicitly public. Previously this view had no authentication_classes
    # set, so it inherited the global DEFAULT_AUTHENTICATION_CLASSES
    # (identity.authentication.JWTAuthentication). If a request to this
    # endpoint carried a stale/invalid Authorization header — which the
    # frontend was attaching unconditionally before its own fix — DRF would
    # reject the request with 401 before this view's post() ever ran, meaning
    # the email/password in the body were never actually checked. A login
    # endpoint must always be reachable regardless of what auth state (valid,
    # expired, or garbage) the caller happens to be carrying.
    authentication_classes = []
    permission_classes = []

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

class RefreshTokenView(APIView):
    """
    Exchanges a still-valid refresh token for a new access token, so a
    provider/patient with the app open doesn't get logged out just because
    an hour passed -- the frontend calls this silently on a 401 instead of
    forcing a full re-login. Only a dead/invalid refresh token (>1 day, or
    tampered) should end in a real logout.
    """
    authentication_classes = []

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {"error": "refresh_token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = jwt.decode(refresh_token, settings.JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("expired refresh token")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("invalid refresh token")

        identity_id = payload.get("user_id")
        try:
            Identity.objects.get(id=identity_id)
        except Identity.DoesNotExist:
            raise AuthenticationFailed("invalid refresh token")

        access_token = generateaccessToken(identity=identity_id)
        return Response({"a_token": access_token}, status=status.HTTP_200_OK)


class SendOTPView(APIView):
    """
    FIX (security): previously took an arbitrary `user` (identity id) from
    the request body with no ownership check AND no rate limiting --
    anyone who had or guessed an identity_id could spam that person's
    inbox indefinitely. Can't require IsAuthenticated the normal way since
    this runs pre-session (part of the login/verify flow), so this is
    fixed with rate limiting instead, keyed by identity_id:

      - COOLDOWN: one send per identity per 60s, so a user double-tapping
        "resend" doesn't invalidate their own in-flight code, and so a
        single spammer can't fire requests back-to-back.
      - HOURLY CAP: max 5 sends per identity per rolling hour, so even
        respecting the cooldown, a spammer can't grind out dozens of
        emails to the same inbox in a short window.

    Ownership (anyone can still trigger a send for an identity_id they
    don't own) is NOT fixed here -- that's inherent to this being a
    pre-session endpoint reachable before any session exists (the
    "forgot my code, resend it" flow can't require being logged in as
    the account it's resending a code for). Rate limiting is the
    correct control for this specific view; it cannot become fully
    ownership-gated without breaking the flow it exists for.
    """

    SEND_COOLDOWN_SECONDS = 60
    SEND_MAX_PER_WINDOW = 5
    SEND_WINDOW_SECONDS = 3600

    def post(self, request):
        if not request.data:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = request.data.get("user")
        if not identity:
            return Response({"error": "user required"}, status=status.HTTP_400_BAD_REQUEST)
        identity = get_object_or_404(Identity, id=identity)
        identity_id = str(identity.id)

        cooldown_key = f"otp:send:cooldown:{identity_id}"
        if cache.get(cooldown_key):
            return Response(
                {"error": "please wait before requesting another code"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        count_key = f"otp:send:count:{identity_id}"
        count = _cache_incr(count_key, self.SEND_WINDOW_SECONDS)
        if count > self.SEND_MAX_PER_WINDOW:
            return Response(
                {"error": "too many code requests, please try again later"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        cache.set(cooldown_key, True, self.SEND_COOLDOWN_SECONDS)

        otp = generate_code(length=6, digits_only=True)
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
    """
    FIX (security): previously took `user` (identity id) from the request
    body with no ownership check and no attempt limiting -- a 6-digit OTP
    is only 1,000,000 possibilities, brute-forceable by an automated
    script hitting this endpoint repeatedly with the same identity_id.

    Fixed with a cache-based lockout keyed by identity_id:
      - After MAX_ATTEMPTS wrong guesses within ATTEMPT_WINDOW_SECONDS,
        the identity is locked out for LOCKOUT_SECONDS -- verification
        attempts return 429 regardless of the code supplied, without
        even checking it against the DB.
      - A successful verification clears both the attempt counter and
        any lockout for that identity.

    Ownership is not (and structurally cannot be) fixed here for the same
    reason as SendOTPView -- this runs before a session exists.
    """

    MAX_ATTEMPTS = 5
    ATTEMPT_WINDOW_SECONDS = 600  # 10 min -- matches the OTP's own expiry
    LOCKOUT_SECONDS = 900  # 15 min

    def post(self, request):
        otp = request.data.get("otp")
        identity = request.data.get("user")
        if not request.data or not otp or not identity:
            return Response({"error": "bad request, please fill in all required fields"}, status=status.HTTP_400_BAD_REQUEST)

        identity_id = str(identity)
        lock_key = f"otp:verify:lock:{identity_id}"
        if cache.get(lock_key):
            return Response(
                {"error": "too many failed attempts, please try again later"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        otp_instance = get_object_or_404(Otp, identity_ref=identity)

        if not otp_instance.code == otp or otp_instance.is_used:
            self._register_failed_attempt(identity_id)
            return Response({"error": "invalid OTP code"}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if now > (otp_instance.created_at + timedelta(minutes=10)):
            return Response({"error": "OTP expired, request another OTP"}, status=status.HTTP_400_BAD_REQUEST)

        otp_instance.is_used = True
        Identity.objects.filter(id=identity).update(email_verified=True)
        otp_instance.save()

        # Success -- clear any accumulated attempt count/lockout so a
        # later legitimate re-verification (e.g. a second OTP flow for
        # this identity down the line) isn't penalised by past failures.
        cache.delete(f"otp:verify:attempts:{identity_id}")
        cache.delete(lock_key)

        return Response({"detail": "OTP verified"}, status=status.HTTP_200_OK)

    def _register_failed_attempt(self, identity_id):
        attempts_key = f"otp:verify:attempts:{identity_id}"
        attempts = _cache_incr(attempts_key, self.ATTEMPT_WINDOW_SECONDS)
        if attempts >= self.MAX_ATTEMPTS:
            cache.set(f"otp:verify:lock:{identity_id}", True, self.LOCKOUT_SECONDS)


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
    """
    Two legitimate callers, two different auth states:

      1. The pre-session login handoff page (apps/web /auth/accounts/{id})
         -- calls this BEFORE any access token exists, using only the
         one-time auth_code LoginView just issued (?auth_tkn=). This is
         the endpoint's ORIGINAL and still-primary use case.
      2. Any already-logged-in app calling this later with a real JWT.

    Uses _identity_authorised(), which accepts EITHER a matching
    authenticated request.user OR a valid, unexpired auth_code for this
    identity via ?auth_tkn=. The auth_code is validated, not consumed --
    TokenView is still what deletes it, whenever the chosen app does its
    own real token exchange later.
    """

    def get(self, request, identity_id):
        if not _identity_authorised(request, identity_id):
            return Response(
                {"error": "You do not have permission to view these accounts"},
                status=status.HTTP_403_FORBIDDEN,
            )

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
        if not _identity_authorised(request, identity_id):
            return Response(
                {"error": "You do not have permission to modify this identity"},
                status=status.HTTP_403_FORBIDDEN,
            )

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

                # ── Sync core fields onto the provider.HealthcareProvider record ──
                # HealthcareProviderAccount (this app) and HealthcareProvider (the
                # provider app) are two separate models. The provider's own profile
                # page, the public "Find a Doctor" list, and public doctor profiles
                # all read from HealthcareProvider, not from this account record —
                # so without this sync, speciality/licence info entered at signup
                # silently never appears anywhere else.
                try:
                    from provider.models import HealthcareProvider
                    provider, _ = HealthcareProvider.objects.get_or_create(identity=identity)
                    if phone_number:
                        provider.phone_number = phone_number
                    speciality = request.data.get("speciality")
                    if speciality:
                        provider.speciality = speciality
                    licence_number = request.data.get("licence_number")
                    if licence_number:
                        provider.licence_number = licence_number
                    licence_type = request.data.get("licence_type")
                    if licence_type:
                        provider.licence_type = licence_type
                    provider.save()
                except Exception:
                    pass

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
    # TODO: this method body is currently just `pass` after the guard
    # clause -- falls through and returns None, which DRF will likely
    # error on. Needs a real implementation; flagging as a separate bug
    # from auth. Added IsAuthenticated as a baseline so this isn't wide
    # open once someone does implement it.
    permission_classes = [IsAuthenticated]

    def post(self, request, account_type, init_model_id):
        if not request.data or account_type not in ACCOUNT_TYPES:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        pass


class DeactivateAccountView(APIView):
    # TODO: currently a no-op -- always returns success without touching
    # the DB. Add an ownership check here once this actually deactivates
    # something. Added IsAuthenticated as a baseline in the meantime.
    permission_classes = [IsAuthenticated]

    def post(self, request, identity_id, account_type):
        if account_type not in ACCOUNT_TYPES:
            return Response({"error": "invalid account type"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "account deactivated successfully"}, status=status.HTTP_200_OK)


class DeactivateIdentityView(APIView):
    """
    FIX: previously no permission_classes -- anyone could deactivate any
    account just by knowing identity_id. Now requires the caller to BE
    that identity.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, identity_id):
        if str(request.user.id) != str(identity_id):
            return Response(
                {"error": "You do not have permission to deactivate this account"},
                status=status.HTTP_403_FORBIDDEN,
            )

        identity = get_object_or_404(Identity, id=identity_id)
        identity.is_active = False
        identity.save()
        return Response({}, status=status.HTTP_204_NO_CONTENT)
