"""Compatibility wrapper for OTP helpers."""

from bloodbank.utils import (  # noqa: F401
    generate_backup_codes,
    generate_manual_otp_code,
    generate_otp_secret,
    generate_qr_code,
    get_otp_expiry_time,
    get_totp_authenticator,
    is_otp_expired,
    use_backup_code,
    verify_otp_token,
)
