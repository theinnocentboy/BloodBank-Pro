"""Utilities for sending emails via SMTP."""

import smtplib
from email.message import EmailMessage
from flask import current_app


def send_verification_email(to_email: str, verify_link: str, subject: str = "Verify your Blood Bank account") -> bool:
    """Send a verification email containing the provided link.

    Returns True on success, False on failure.
    """
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("EMAIL_FROM")
    msg["To"] = to_email
    msg.set_content(
        f"Hello,\n\nPlease verify your email by clicking the link below:\n\n{verify_link}\n\nIf you did not register, please ignore this email.\n"
    )

    if not cfg.get("SMTP_SERVER"):
        current_app.logger.warning(
            "SMTP_SERVER is not configured. Verification link for %s: %s",
            to_email,
            verify_link,
        )
        return False

    try:
        server = smtplib.SMTP(cfg.get("SMTP_SERVER"), cfg.get("SMTP_PORT"))
        server.ehlo()
        if cfg.get("SMTP_USE_TLS"):
            server.starttls()
            server.ehlo()
        username = cfg.get("SMTP_USERNAME")
        password = cfg.get("SMTP_PASSWORD")
        if username:
            server.login(username, password)
        server.send_message(msg)
        server.quit()
        current_app.logger.info(f"Verification email sent to {to_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send verification email to {to_email}: {e}")
        return False
