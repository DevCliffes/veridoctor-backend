"""Custom JWT authentication for the identity app.

Decodes the access token issued by `generateaccessToken` (see
identity/utils.py) and resolves it to the corresponding Identity, so
DRF's permission classes (IsAuthenticated, etc.) have a real
request.user to check against. This replaces DRF's built-in
TokenAuthentication, which was configured but never functional here
since rest_framework.authtoken isn't installed and the app issues its
own JWTs rather than DRF's token model.
"""
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import Identity

JWT_SECRET = settings.JWT_SECRET


class JWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            # No token on the request — return None so DRF treats this
            # as an anonymous request and lets the view's permission
            # classes decide whether that's allowed.
            return None

        token = auth_header
        if auth_header.startswith(f"{self.keyword} "):
            token = auth_header[len(self.keyword) + 1 :]

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Access token has expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid access token.")

        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationFailed("Invalid token payload.")

        try:
            identity = Identity.objects.get(id=user_id, is_active=True)
        except Identity.DoesNotExist:
            raise AuthenticationFailed("User not found or inactive.")
        except (ValueError, Identity.MultipleObjectsReturned):
            raise AuthenticationFailed("Invalid token payload.")

        return (identity, token)

    def authenticate_header(self, request):
        return self.keyword
