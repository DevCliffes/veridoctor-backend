import os
import json
import urllib.request
import urllib.error

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "VeriDoctor <noreply@veridoctor.com>")
RESEND_API_URL = "https://api.resend.com/emails"


def _send_via_resend(to_email: str, subject: str, html_body: str) -> bool:
    """
    Shared low-level sender used by both send_otp_email() and
    send_appointment_reminder_email() — one place to keep the actual
    HTTP call, headers, and error handling in sync.
    Returns True on success, False on failure — never raises.
    """
    if not RESEND_API_KEY:
        print("RESEND_API_KEY is not set — cannot send email")
        return False
    payload = {
        "from": DEFAULT_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "VeriDoctor-Backend/1.0 (+https://veridoctor.com)",
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


def send_otp_email(to_email: str, otp_code: str) -> bool:
    """
    Sends an OTP verification email via Resend's REST API using only
    the standard library (no extra Poetry dependency needed, so this
    doesn't require a poetry.lock update).
    Returns True on success, False on failure — never raises, so a
    failed email doesn't crash the calling request.
    """
    html_body = f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
            <h2 style="color: #2563EB;">VeriDoctor</h2>
            <p>Your verification code is:</p>
            <p style="font-size: 32px; font-weight: bold; letter-spacing: 4px;">{otp_code}</p>
            <p style="color: #6b7280; font-size: 14px;">This code expires in 10 minutes. If you didn't request this, you can safely ignore this email.</p>
        </div>
    """
    return _send_via_resend(to_email, "Your VeriDoctor verification code", html_body)


def send_appointment_reminder_email(to_email: str, subject: str, message: str) -> bool:
    """
    Sends an appointment reminder email via Resend — same transport as
    send_otp_email(), just a different subject/body. Used by
    notifications/services.py's send_email_reminder().
    """
    html_body = f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
            <h2 style="color: #2563EB;">VeriDoctor</h2>
            <p>{message}</p>
        </div>
    """
    return _send_via_resend(to_email, subject, html_body)
