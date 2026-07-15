import os
import json
import urllib.request
import urllib.error

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "VeriDoctor <noreply@veridoctor.com>")

RESEND_API_URL = "https://api.resend.com/emails"


def send_otp_email(to_email: str, otp_code: str) -> bool:
    """
    Sends an OTP verification email via Resend's REST API using only
    the standard library (no extra Poetry dependency needed, so this
    doesn't require a poetry.lock update).
    Returns True on success, False on failure — never raises, so a
    failed email doesn't crash the calling request.
    """
    if not RESEND_API_KEY:
        print("RESEND_API_KEY is not set — cannot send OTP email")
        return False

    payload = {
        "from": DEFAULT_FROM_EMAIL,
        "to": [to_email],
        "subject": "Your VeriDoctor verification code",
        "html": f"""
            <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
                <h2 style="color: #2563EB;">VeriDoctor</h2>
                <p>Your verification code is:</p>
                <p style="font-size: 32px; font-weight: bold; letter-spacing: 4px;">{otp_code}</p>
                <p style="color: #6b7280; font-size: 14px;">This code expires in 10 minutes. If you didn't request this, you can safely ignore this email.</p>
            </div>
        """,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Resend API error sending to {to_email}: {e.code} {body}")
        return False
    except urllib.error.URLError as e:
        print(f"Failed to reach Resend API for {to_email}: {e.reason}")
        return False
