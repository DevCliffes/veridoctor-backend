"""utilities for the identity app"""

from .models import AuthCode, Identity
import jwt
from django.utils import timezone
import datetime
from django.conf import settings

JWT_SECRET = settings.JWT_SECRET


def generateAuthCode(identity: Identity) -> str:
    """generates and persists a temporary authentication code to be used for token generation"""
    jwt_payload = {
        "user_id": str(identity.id),
        "iat": timezone.now().timestamp(),
        "exp": (timezone.now() + datetime.timedelta(minutes=5)).timestamp(),
    }

    code = jwt.encode(jwt_payload, JWT_SECRET, algorithm="HS256")
    # remove an existing auth_code if it exists
    # assumes a user logs in twice we invalidate the previous login
    try:
        auth_code = AuthCode.objects.get(identity__id=identity.id)
        auth_code.delete()
    except AuthCode.DoesNotExist:
        pass
    AuthCode.objects.create(identity=identity, code=code)

    return code


def generateaccessToken(identity: str) -> str:
    """generates a jwt access token"""
    jwt_payload = {
        "user_id": str(identity),
        "iat": timezone.now().timestamp(),
        "exp": (timezone.now() + datetime.timedelta(hours=1)).timestamp(),
    }
    a_token = jwt.encode(jwt_payload, JWT_SECRET, algorithm="HS256")
    return a_token


def generaterefreshtoken(identity: str) -> str:
    """generates a jwt refresh token"""
    jwt_payload = {
        "user_id": str(identity),
        "iat": timezone.now().timestamp(),
        "exp": (timezone.now() + datetime.timedelta(days=1)).timestamp(),
    }
    a_token = jwt.encode(jwt_payload, JWT_SECRET, algorithm="HS256")
    return a_token
