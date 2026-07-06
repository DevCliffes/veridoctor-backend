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
    # FIX: previously did a separate get()+delete() then create(). Two
    # near-simultaneous login calls for the same identity (double-click,
    # frontend retry, a page reload mid-flow) could both pass the "does
    # it exist" check, both delete, then both try to create -- and since
    # AuthCode.identity is a OneToOneField, the loser hit IntegrityError,
    # which LoginView turned into a raw 500. The winner also left a row
    # behind that the loser never received a code for, so that identity's
    # login was permanently stuck until the row was manually deleted.
    # update_or_create is a single atomic UPDATE-or-INSERT under the row
    # lock, so concurrent calls can no longer race each other.
    AuthCode.objects.update_or_create(identity=identity, defaults={"code": code})
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
