from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import os
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from datetime import datetime
import re
from bloodbank.constants import VALID_ROLES
from bloodbank.extensions import db
from bloodbank.models import User
from bloodbank.otp_utils import generate_manual_otp_code, get_otp_expiry_time, verify_otp_token, is_otp_expired
from bloodbank.auth0_utils import oauth, get_auth0_user_info, is_auth0_enabled
from bloodbank.email_utils import send_otp_email
from bloodbank.sms_utils import send_sms_otp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bloodbank.routes.user import is_moderate_password
from bloodbank.services.auth_service import (
    confirm_phone_otp as auth_confirm_phone_otp,
    forgot_password as auth_forgot_password,
    login_user as auth_login_user,
    register_user as auth_register_user,
    resend_email_otp as auth_resend_email_otp,
    reset_password as auth_reset_password,
    send_phone_verification as auth_send_phone_verification,
    verify_email_gate as auth_verify_email_gate,
    verify_otp as auth_verify_otp,
)



auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        result = auth_login_user(request.form, session)
        for category, message in result.get("flash_messages", []):
            flash(message, category)
        if result.get("redirect"):
            return redirect(url_for(result["redirect"]))

    return render_template("login.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    """Verify OTP code (either from authenticator or manual entry)."""
    if request.method == "POST":
        result = auth_verify_otp(request.form, session)
        for category, message in result.get("flash_messages", [(result.get("category"), result.get("message"))]):
            if message:
                flash(message, category)
        if result.get("redirect"):
            return redirect(url_for(result["redirect"]))
    
    return render_template("verify-otp.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        result = auth_register_user(request.form, session)
        for category, message in result.get("flash_messages", []):
            flash(message, category)
        if result.get("redirect"):
            return redirect(url_for(result["redirect"]))

    return render_template("register.html")

@auth_bp.route("/auth0/login")
@auth_bp.route("/auth0/login/<provider>")
def login_with_auth0(provider=None):
    if not is_auth0_enabled():
        flash("Auth0 integration is not configured. Please use the regular login.", "warning")
        return redirect(url_for("auth.login"))
    
    try:
        callback_url = current_app.config.get('AUTH0_CALLBACK_URL')
        if not callback_url:
            callback_url = url_for("auth.auth0_callback", _external=True)
        
        auth0_client = oauth.create_client('auth0')
        
        if provider:
            return auth0_client.authorize_redirect(redirect_uri=callback_url, connection=provider)
        else:
            return auth0_client.authorize_redirect(redirect_uri=callback_url)
    except Exception as e:
        current_app.logger.error(f"Auth0 login error: {e}")
        flash("Error connecting to Auth0. Please use the standard login.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth0/callback")
def auth0_callback():
    if not is_auth0_enabled():
        flash("Auth0 is not configured.", "danger")
        return redirect(url_for("auth.login"))
    
    try:
        auth0_client = oauth.create_client('auth0')
        token = auth0_client.authorize_access_token()
        userinfo = token.get('userinfo')
        
        if not userinfo:
            flash("Failed to retrieve user information from Auth0.", "danger")
            return redirect(url_for("auth.login"))
        
        # Extract basic user info from your helper
        user_data = get_auth0_user_info(userinfo)
        email = user_data['email']
        full_name = user_data['full_name']
        auth0_id = user_data['auth0_id']

        # --- NEW: Extract Picture, Gender, and DOB directly from userinfo ---
        picture_url = userinfo.get("picture")
        auth_gender = userinfo.get("gender")
        auth_dob_raw = userinfo.get("birthdate")

        # Parse DOB safely into a Python date object
        auth_dob = None
        if auth_dob_raw:
            try:
                auth_dob = datetime.strptime(auth_dob_raw, "%Y-%m-%d").date()
            except ValueError:
                pass # Failsafe if the date format is unexpected
        # --------------------------------------------------------------------
        
        # Find or create user
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Update existing user name if needed
            user.full_name = full_name
            # NEW: Add the picture to existing users if they don't have one
            if not user.profile_pic and picture_url:
                user.profile_pic = picture_url

            if not user.gender and auth_gender:
                user.gender = auth_gender.capitalize()
                
            if not user.dob and auth_dob:
                user.dob = auth_dob
            # -----------------------------------------------------
                
            # Link the Auth0 ID so they are recognized as a social account
            user.auth0_id = auth0_id
            db.session.commit()
        else:
            # Create new user
            username = email.split('@')[0]
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{email.split('@')[0]}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                email_verified=True,
                role='user',
                phone=None,  # Explicitly set to None for new OAuth users
                profile_pic=picture_url,                                  # <-- NEW
                gender=auth_gender.capitalize() if auth_gender else None, # <-- NEW
                dob=auth_dob                                              # <-- NEW
            )
            user.set_password(os.urandom(32).hex())
            db.session.add(user)
            db.session.commit()
        
        # Set session data
        session.clear()
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        session["auth0_id"] = auth0_id
        
        # Check for missing phone number (Mandatory for BloodBank)
        if not user.phone:
            flash("Welcome! Please complete your profile by adding your phone number.", "info")
            
        flash(f"Welcome, {user.full_name}!", "success")
        
        if user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("user.dashboard"))
        
    except Exception as e:
        current_app.logger.error(f"Auth0 callback error: {e}")
        flash("Authentication failed. Please try again.", "danger")
        return redirect(url_for("auth.login"))

@auth_bp.route("/logout")
def logout():
    auth0_id = session.get("auth0_id")
    session.clear()
    
    if auth0_id and is_auth0_enabled():
        auth0_domain = current_app.config.get('AUTH0_DOMAIN')
        client_id = current_app.config.get('AUTH0_CLIENT_ID')
        if auth0_domain and client_id:
            return redirect(
                f"https://{auth0_domain}/v2/logout?"
                f"client_id={client_id}&"
                f"returnTo={url_for('main.home', _external=True)}"
            )
    
    flash("Logged out successfully.", "success")
    return redirect(url_for("main.home"))


# ==========================================
# 1. EMAIL VERIFICATION (The New Hard Gate)
# ==========================================
@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email_gate():
    """Validates the Email code before allowing app entry."""
    if request.method == "POST":
        result = auth_verify_email_gate(request.form, session)
        flash(result["message"], result["category"])
        if result.get("render"):
            return render_template(result["render"], **result.get("context", {}))
        if result.get("redirect"):
            return redirect(url_for(result["redirect"]))

    pending_user_id = session.get("pending_user_id")
    user = db.session.get(User, pending_user_id) if pending_user_id else None
    if not user:
        flash("Session expired. Please log in again.", "danger")
        return redirect(url_for("auth.login"))
    return render_template("verify-email.html", email=user.email)


@auth_bp.route("/resend-email-otp", methods=["POST", "GET"]) 
def resend_email_otp():
    result = auth_resend_email_otp(session)
    flash(result["message"], result["category"])
    return redirect(url_for(result["redirect"]))


# ==========================================
# 2. PHONE VERIFICATION (The New Soft Gate)
# ==========================================
@auth_bp.route("/verify-phone/send", methods=["GET"])
def send_phone_verification():
    """Triggered from the dashboard/profile to send the SMS OTP."""
    result = auth_send_phone_verification(session)
    if result["message"]:
        flash(result["message"], result["category"])
    return redirect(url_for(result["redirect"]))


@auth_bp.route("/verify-phone/confirm", methods=["GET", "POST"])
def confirm_phone_otp():
    """Validates the SMS code from logged-in users."""
    if request.method == "POST":
        result = auth_confirm_phone_otp(request.form, session)
        flash(result["message"], result["category"])
        if result["success"]:
            return redirect(url_for("user.dashboard"))

    user = db.session.get(User, session.get("user_id"))
    if not user:
        return redirect(url_for("auth.login"))
    return render_template("verify-phone.html", phone=user.phone)

# ==========================================
# GLOBAL TEMPLATE VARIABLES
# ==========================================
@auth_bp.app_context_processor
def inject_global_user():
    """Injects the logged-in user into all templates automatically."""
    if 'user_id' in session:
        global_user = db.session.get(User, session.get('user_id'))
        return dict(global_user=global_user)
    return dict(global_user=None)

# ==========================================
# PASSWORD RESET LOGIC
# ==========================================

def get_reset_token(user, expires_sec=1800):
    """Generates a secure token valid for 30 minutes."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps({'user_id': user.id}, salt='password-reset-salt')

def verify_reset_token(token, expires_sec=1800):
    """Verifies the token and returns the user if valid."""
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = s.loads(token, salt='password-reset-salt', max_age=expires_sec)['user_id']
    except Exception:
        return None
    return db.session.get(User, user_id)

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
        
    if request.method == 'POST':
        result = auth_forgot_password(request.form.get('email', '').strip())
        flash(result["message"], result["category"])
        return redirect(url_for(result["redirect"]))
        
    return render_template('forgot-password.html')

@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
        
    if request.method == 'POST':
        result = auth_reset_password(token, request.form)
        flash(result["message"], result["category"])
        if result.get("redirect"):
            return redirect(url_for(result["redirect"]))

    user = verify_reset_token(token)
    if not user:
        flash("That is an invalid or expired token. Please request a new one.", "danger")
        return redirect(url_for('auth.forgot_password'))

    return render_template('reset-password.html', token=token)

def send_real_email(recipient_email, reset_url):
    sender_email = os.environ.get("SMTP_USERNAME", "")  # Put your email here
    app_password = os.environ.get("SMTP_PASSWORD", "") # Put your App Password here
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = "BloodBank - Password Reset Request"
    
    body = f"""
    Hello,
    
    You have requested to reset your password. Click the link below to set a new one:
    
    {reset_url}
    
    If you did not make this request, please ignore this email.
    """
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email failed to send: {e}")
        return False