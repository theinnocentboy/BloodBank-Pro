"""Shared stateless helpers for BloodBank."""

from __future__ import annotations

import base64
import os
import requests
import re
import secrets
import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO

import pyotp
import qrcode
from flask import current_app



def calculate_age(born):
    """Calculate exact age from a date of birth."""
    if not born:
        return 0
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def is_moderate_password(password):
    """Check that a password is 8+ chars and contains upper, lower, and digit."""
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    return True


def allowed_file(filename, allowed_extensions=None):
    """Validate file extension against the configured allow-list."""
    if not filename or "." not in filename:
        return False
    extensions = allowed_extensions or current_app.config.get(
        "ALLOWED_EXTENSIONS", {"pdf", "png", "jpg", "jpeg"}
    )
    return filename.rsplit(".", 1)[1].lower() in extensions


def send_real_email(recipient_email, reset_url):
    """Send a password-reset email using the Resend HTTP API."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    sender_email = "noreply@bloodbankpro.software"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "from": f"BloodBank Pro <{sender_email}>",
        "to": [recipient_email],
        "subject": "BloodBank Pro - Password Reset Request",
        "html": f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Password Reset Request</h2>
            <p>Hello,</p>
            <p>You have requested to reset your password. Click the button below to set a new one:</p>
            <p style="margin: 20px 0;">
                <a href="{reset_url}" style="background-color: #e63946; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Reset Password
                </a>
            </p>
            <p style="color: #666; font-size: 12px;">If the button above doesn't work, copy and paste this URL into your browser:</p>
            <p style="color: #666; font-size: 12px;">{reset_url}</p>
            <p style="color: #999; font-size: 12px; margin-top: 20px;">If you did not make this request, please ignore this email.</p>
        </div>
        """
    }

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            json=payload,
            headers=headers,
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Password reset email error: {e}")
        return False


def generate_otp_secret():
    """Generate a new OTP secret key."""
    return pyotp.random_base32()


def get_totp_authenticator(username, secret, issuer="Blood Bank Management"):
    """Get a TOTP authenticator object."""
    return pyotp.TOTP(secret)


def generate_qr_code(username, secret, issuer="Blood Bank Management"):
    """Generate a base64-encoded QR code for OTP setup."""
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name=issuer)

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def verify_otp_token(secret, token, window=1):
    """Verify a time-based OTP token."""
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=window)
    except Exception:
        return False


def generate_manual_otp_code():
    """Generate a random 6-digit OTP code."""
    return str(secrets.randbelow(1000000)).zfill(6)


def get_otp_expiry_time(seconds=300):
    """Return the UTC expiry timestamp for an OTP."""
    return datetime.utcnow() + timedelta(seconds=seconds)


def is_otp_expired(expiry_time):
    """Check whether an OTP expiry timestamp is in the past."""
    return datetime.utcnow() > expiry_time


def generate_backup_codes(count=10):
    """Generate comma-separated recovery codes for OTP backup."""
    codes = [secrets.token_urlsafe(6) for _ in range(count)]
    return ",".join(codes)


def use_backup_code(backup_codes_str, code):
    """Remove a used backup code from the stored list."""
    if not backup_codes_str:
        return None

    codes = backup_codes_str.split(",")
    if code in codes:
        codes.remove(code)
        return ",".join(codes)

    return None