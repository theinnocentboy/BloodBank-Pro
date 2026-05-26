from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from bloodbank.extensions import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), default="user")
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Auth0 Fields
    auth0_id = db.Column(db.String(255), unique=True)
    
    # OTP Fields
    otp_secret = db.Column(db.String(255))  # Base32 encoded secret
    otp_enabled = db.Column(db.Boolean, default=False)
    otp_backup_codes = db.Column(db.Text)  # Comma-separated backup codes
    otp_verified_at = db.Column(db.DateTime)
    
    # OTP for manual entry (temporary OTP)
    manual_otp_code = db.Column(db.String(6))
    manual_otp_expires_at = db.Column(db.DateTime)

    donor_profile = db.relationship(
        "Donor", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    blood_requests = db.relationship(
        "BloodRequest", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


class Donor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    blood_group = db.Column(db.String(5), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    availability = db.Column(db.Boolean, default=True)
    last_donation = db.Column(db.DateTime)
    units_donated = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # AI/ML Fields - Location-based matching
    latitude = db.Column(db.Float, nullable=True)  # For geolocation
    longitude = db.Column(db.Float, nullable=True)  # For geolocation
    donation_frequency = db.Column(db.Integer, default=0)  # For activity scoring

    user = db.relationship("User", back_populates="donor_profile")


class BloodRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    blood_group = db.Column(db.String(5), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="pending")
    urgency = db.Column(db.String(20), default="normal")
    reason = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # AI/ML Fields - Emergency priority and predictions
    priority_score = db.Column(db.Float, default=0.0)  # AI-computed urgency score
    emergency_keywords = db.Column(db.String(255), nullable=True)  # Detected keywords
    predicted_fulfillment_time = db.Column(db.Integer, nullable=True)  # Hours to fulfill
    is_emergency = db.Column(db.Boolean, default=False)  # AI-flagged emergency

    user = db.relationship("User", back_populates="blood_requests")


class BloodInventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blood_group = db.Column(db.String(5), unique=True, nullable=False)
    units = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # AI/ML Fields - Demand prediction
    predicted_demand = db.Column(db.Integer, nullable=True)  # ML-predicted units needed
    shortage_risk = db.Column(db.Boolean, default=False)  # Shortage warning


class ChatConversation(db.Model):
    """Stores AI chatbot conversation history."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)  # User message
    response = db.Column(db.Text, nullable=False)  # AI response
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship("User")


class DonorRecommendation(db.Model):
    """Logs donor recommendation requests and results for analytics."""
    id = db.Column(db.Integer, primary_key=True)
    blood_request_id = db.Column(db.Integer, db.ForeignKey("blood_request.id"))
    recommended_donor_id = db.Column(db.Integer, db.ForeignKey("donor.id"))
    recommendation_score = db.Column(db.Float)
    ranking = db.Column(db.Integer)  # 1st, 2nd, 3rd recommendation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    blood_request = db.relationship("BloodRequest")
    donor = db.relationship("Donor")

