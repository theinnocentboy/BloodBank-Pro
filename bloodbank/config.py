import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
    
    # Ensure instance directory exists and use proper path
    instance_path = BASE_DIR / 'instance'
    instance_path.mkdir(parents=True, exist_ok=True)
    db_path = instance_path / 'blood.db'
    
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
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
    SMTP_USE_TLS = _env_bool(os.environ.get("SMTP_USE_TLS"), False)
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "")

    # Document Upload Configuration
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'instance', 'uploads', 'requisitions')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
