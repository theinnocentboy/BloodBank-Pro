"""Utilities for sending emails via SMTP."""

import smtplib
from email.message import EmailMessage
from flask import current_app
import logging
from pathlib import Path

# Create a file logger for email debugging
LOG_FILE = Path(__file__).resolve().parent.parent / "instance" / "email_debug.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

email_logger = logging.getLogger('email_utils')
email_logger.setLevel(logging.DEBUG)
email_logger.addHandler(file_handler)


def send_verification_email(to_email: str, verify_link: str, subject: str = "Verify your Blood Bank account") -> bool:
    """Send a verification email containing the provided link.

    Returns True on success, False on failure.
    """
    email_logger.info(f"send_verification_email called for {to_email}")
    
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("EMAIL_FROM")
    msg["To"] = to_email
    msg.set_content(
        f"Hello,\n\nPlease verify your email by clicking the link below:\n\n{verify_link}\n\nIf you did not register, please ignore this email.\n"
    )

    if not cfg.get("SMTP_SERVER"):
        email_logger.warning(
            "SMTP_SERVER is not configured. Verification link for %s: %s",
            to_email,
            verify_link,
        )
        current_app.logger.warning(
            "SMTP_SERVER is not configured. Verification link for %s: %s",
            to_email,
            verify_link,
        )
        return False

    try:
        smtp_server = cfg.get("SMTP_SERVER")
        smtp_port = cfg.get("SMTP_PORT")
        smtp_user = cfg.get("SMTP_USERNAME")
        smtp_pass = cfg.get("SMTP_PASSWORD")
        use_tls = cfg.get("SMTP_USE_TLS")
        
        email_logger.info(f"Connecting to SMTP: {smtp_server}:{smtp_port} (TLS={use_tls})")
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        email_logger.info("EHLO successful")
        
        if use_tls:
            email_logger.info("Starting TLS...")
            server.starttls()
            server.ehlo()
            email_logger.info("TLS started and EHLO successful")
        
        if smtp_user:
            email_logger.info(f"Logging in as {smtp_user}")
            server.login(smtp_user, smtp_pass)
            email_logger.info("Login successful")
        
        email_logger.info(f"Sending email to {to_email}")
        server.send_message(msg)
        server.quit()
        
        email_logger.info(f"Verification email sent to {to_email}")
        current_app.logger.info(f"Verification email sent to {to_email}")
        return True
    except Exception as e:
        email_logger.error(f"Failed to send verification email to {to_email}: {type(e).__name__}: {e}", exc_info=True)
        current_app.logger.error(f"Failed to send verification email to {to_email}: {type(e).__name__}: {e}")
        return False
