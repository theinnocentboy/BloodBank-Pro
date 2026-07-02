"""OTP Utilities for Two-Factor Authentication"""

import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from io import BytesIO


def generate_otp_secret():
    """Generate a new OTP secret key."""
    return pyotp.random_base32()


def get_totp_authenticator(username, secret, issuer="Blood Bank Management"):
    """Get TOTP authenticator object."""
    return pyotp.TOTP(secret)


def generate_qr_code(username, secret, issuer="Blood Bank Management"):
    """Generate QR code for OTP setup.
    
    Returns base64 encoded PNG image.
    """
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username,
        issuer_name=issuer
    )
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return qr_code_base64


def verify_otp_token(secret, token, window=1):
    """Verify OTP token using time-based OTP.
    
    Args:
        secret: The OTP secret key
        token: The 6-digit code to verify
        window: Number of time windows to check (before and after current)
    
    Returns:
        True if token is valid, False otherwise
    """
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=window)
    except Exception:
        return False


def generate_manual_otp_code():
    """Generate a random 6-digit OTP code for manual entry."""
    import secrets
    return str(secrets.randbelow(1000000)).zfill(6)


def get_otp_expiry_time(seconds=300):
    """Get OTP expiry timestamp (default 5 minutes from now)."""
    return datetime.utcnow() + timedelta(seconds=seconds)


def is_otp_expired(expiry_time):
    """Check if OTP code is expired."""
    return datetime.utcnow() > expiry_time


def generate_backup_codes(count=10):
    """Generate backup codes for account recovery.
    
    Returns:
        Comma-separated string of backup codes
    """
    import secrets
    codes = [secrets.token_urlsafe(6) for _ in range(count)]
    return ",".join(codes)


def use_backup_code(backup_codes_str, code):
    """Mark a backup code as used by removing it from the list.
    
    Returns:
        Updated backup codes string, or None if code not found
    """
    if not backup_codes_str:
        return None
    
    codes = backup_codes_str.split(",")
    if code in codes:
        codes.remove(code)
        return ",".join(codes)
    
    return None
