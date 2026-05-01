"""
otp_utils.py
============
Central helper for all OTP operations.

Phone OTP  → Firebase Auth REST API  (primary)
Email OTP  → Brevo (Sendinblue) Transactional API  (fallback / alternative)

Environment variables / Django settings required
------------------------------------------------
BREVO_API_KEY          – your Brevo v3 API key
BREVO_SENDER_EMAIL     – verified sender address in Brevo
BREVO_SENDER_NAME      – display name for the sender   (default: "NHEA Voting")
FIREBASE_WEB_API_KEY   – Firebase project Web API key  (from Project Settings → General)

All keys live in your .env / environment; never hard-code them.
"""

import random
import string
import hashlib
import time
import requests
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ── OTP config ────────────────────────────────────────────────────────────────
OTP_LENGTH       = 6
OTP_TTL_SECONDS  = 300   # 5 minutes
OTP_CACHE_PREFIX = "nhea_otp_"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    """Return a zero-padded numeric OTP string."""
    return ''.join(random.choices(string.digits, k=OTP_LENGTH))


def _cache_key(identifier: str) -> str:
    """Stable, collision-resistant cache key for an email/phone."""
    hashed = hashlib.sha256(identifier.encode()).hexdigest()[:16]
    return f"{OTP_CACHE_PREFIX}{hashed}"


def _store_otp(identifier: str, otp: str) -> None:
    cache.set(_cache_key(identifier), otp, timeout=OTP_TTL_SECONDS)


def verify_otp(identifier: str, submitted_otp: str) -> bool:
    """
    Return True if the submitted OTP matches the stored one and has not expired.
    Deletes the OTP from cache on success (single-use).
    """
    key   = _cache_key(identifier)
    stored = cache.get(key)
    if stored and stored == submitted_otp.strip():
        cache.delete(key)
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Email OTP via Brevo
# ─────────────────────────────────────────────────────────────────────────────

def send_email_otp(email: str, voter_name: str = "Delegate") -> bool:
    """
    Generate an OTP, store it, and send it to `email` via Brevo.
    Returns True on success, False on failure.
    """
    otp = _generate_otp()
    _store_otp(email, otp)

    api_key      = getattr(settings, "BREVO_API_KEY", "")
    sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "noreply@nhea.ng")
    sender_name  = getattr(settings, "BREVO_SENDER_NAME", "NHEA Voting")

    if not api_key:
        logger.error("BREVO_API_KEY is not configured.")
        return False

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": email, "name": voter_name}],
        "subject": f"NHEA Voting – Your Email Verification Code: {otp}",
        "htmlContent": _email_html(voter_name, otp),
        "textContent": (
            f"Hello {voter_name},\n\n"
            f"Your NHEA email verification code is: {otp}\n\n"
            f"This code expires in 5 minutes.\n\n"
            f"If you did not request this, please ignore this message."
        ),
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={
                "accept":       "application/json",
                "content-type": "application/json",
                "api-key":      api_key,
            },
            timeout=10,
        )
        if response.status_code in (200, 201):
            logger.info("Brevo email OTP sent to %s", email)
            return True
        logger.error("Brevo error %s: %s", response.status_code, response.text)
        return False
    except requests.RequestException as exc:
        logger.error("Brevo request failed: %s", exc)
        return False


def _email_html(name: str, otp: str) -> str:
    """Branded HTML email body."""
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f0f7f4;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;
                    box-shadow:0 8px 40px rgba(10,79,60,0.12);">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0a4f3c,#1a7a5e);
                     padding:32px 40px;text-align:center;">
            <h1 style="color:#fff;font-size:22px;margin:0 0 6px;">NHEA Voting Platform</h1>
            <p style="color:rgba(255,255,255,0.7);font-size:13px;margin:0;">
              Nigerian Healthcare Excellence Awards
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px;">
            <p style="font-size:16px;color:#1a2e28;margin:0 0 8px;">Hello, <strong>{name}</strong></p>
            <p style="font-size:14px;color:#4a6560;line-height:1.6;margin:0 0 28px;">
              Use the verification code below to confirm your email address
              and access the NHEA voting portal.
            </p>

            <!-- OTP Box -->
            <div style="background:#f0faf5;border:2px dashed #1a7a5e;border-radius:12px;
                        padding:24px;text-align:center;margin-bottom:28px;">
              <p style="font-size:12px;font-weight:700;letter-spacing:1px;
                        text-transform:uppercase;color:#4a6560;margin:0 0 10px;">
                Your Verification Code
              </p>
              <p style="font-family:'Courier New',monospace;font-size:42px;font-weight:700;
                        color:#0a4f3c;letter-spacing:10px;margin:0;">{otp}</p>
              <p style="font-size:12px;color:#4a6560;margin:12px 0 0;">
                ⏱ Expires in <strong>5 minutes</strong>
              </p>
            </div>

            <p style="font-size:13px;color:#8a9e99;line-height:1.6;margin:0;">
              If you did not request this code, please ignore this email.
              Your account will remain secure.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fdf9;padding:20px 40px;text-align:center;
                     border-top:1px solid #e0ede8;">
            <p style="font-size:12px;color:#8a9e99;margin:0;">
              © {_year()} Nigerian Healthcare Excellence Awards &nbsp;|&nbsp;
              Do not reply to this email
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _year():
    from django.utils import timezone
    return timezone.now().year


# ─────────────────────────────────────────────────────────────────────────────
# Phone OTP via Firebase Auth REST API
# ─────────────────────────────────────────────────────────────────────────────
#
# Firebase handles the actual SMS delivery.  The flow:
#   1. Frontend calls firebase.auth().signInWithPhoneNumber(phone, recaptchaVerifier)
#      — this is a CLIENT-SIDE operation using the Firebase JS SDK.
#   2. Firebase sends the SMS and returns a confirmationResult to the browser.
#   3. User types the 6-digit code from the SMS.
#   4. Frontend calls confirmationResult.confirm(code) which returns an idToken.
#   5. Frontend POSTs that idToken to our Django verify_phone_otp view.
#   6. Django verifies the idToken with Firebase Admin SDK → marks is_phone_verified.
#
# Therefore, the server-side work for phone is TOKEN VERIFICATION, not sending.
# The functions below handle step 6.
# ─────────────────────────────────────────────────────────────────────────────

def verify_firebase_id_token(id_token: str) -> dict | None:
    """
    Verify a Firebase ID token using the Firebase Admin SDK.
    Returns the decoded token dict on success, None on failure.

    Requires firebase-admin to be installed and initialised in settings.py:

        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_JSON_PATH)
        firebase_admin.initialize_app(cred)
    """
    try:
        from firebase_admin import auth as firebase_auth
        decoded = firebase_auth.verify_id_token(id_token)
        return decoded
    except Exception as exc:
        logger.error("Firebase token verification failed: %s", exc)
        return None


def get_phone_from_token(decoded_token: dict) -> str | None:
    """Extract the phone number from a decoded Firebase token."""
    return decoded_token.get("phone_number")