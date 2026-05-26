import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
    _db_path = str(BASE_DIR / 'instance' / 'blood.db').replace('\\', '/')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{_db_path}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Auth0 Configuration
    AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
    AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "")
    AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")
    AUTH0_API_AUDIENCE = os.environ.get("AUTH0_API_AUDIENCE", "")
    AUTH0_CALLBACK_URL = os.environ.get("AUTH0_CALLBACK_URL", "http://localhost:5000/auth0/callback")
    
    # OTP Configuration
    OTP_ISSUER_NAME = "Blood Bank Management"
    OTP_WINDOW = 1  # Allow 1 window before and after for time-based OTP
    OTP_EXPIRY_SECONDS = 300  # OTP codes expire after 5 minutes for manual entry

    # SMTP / Email configuration
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@example.com")
