from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime
from typing import Tuple

from bloodbank.constants import VALID_ROLES
from bloodbank.extensions import db
from bloodbank.models import User
from bloodbank.otp_utils import (
    generate_manual_otp_code, 
    get_otp_expiry_time, 
    is_otp_expired,
    verify_otp_token
)
from bloodbank.auth0_utils import oauth, get_auth0_user_info
from bloodbank.email_utils import send_verification_email

auth_bp = Blueprint("auth", __name__)


def _smtp_configured() -> bool:
    return bool(current_app.config.get("SMTP_SERVER"))


def _build_verification_link(email: str) -> str:
    serializer = URLSafeTimedSerializer(current_app.config.get("SECRET_KEY"))
    token = serializer.dumps(email, salt="email-verify")
    return url_for("auth.verify_email", token=token, _external=True)


def _send_verification_email(user: User) -> Tuple[bool, str]:
    verify_link = _build_verification_link(user.email)
    return send_verification_email(user.email, verify_link), verify_link


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("auth.login"))

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            # Require email verification for local accounts
            if not user.email_verified:
                if not _smtp_configured():
                    user.email_verified = True
                    db.session.commit()
                    flash("Email verification is disabled in local mode, so your account is now active.", "info")
                else:
                    sent, _ = _send_verification_email(user)
                    if sent:
                        flash("Your email is not verified yet. We sent a new verification link.", "warning")
                    else:
                        flash("Your email is not verified yet, and the verification email could not be sent. Check SMTP settings or verify from the logged link.", "warning")
                    return redirect(url_for("auth.login"))

            # If OTP is enabled, redirect to OTP verification
            if user.otp_enabled:
                session["pending_user_id"] = user.id
                session["login_time"] = datetime.utcnow().isoformat()
                # Generate and send manual OTP
                otp_code = generate_manual_otp_code()
                user.manual_otp_code = otp_code
                user.manual_otp_expires_at = get_otp_expiry_time(300)  # 5 minutes
                db.session.commit()
                flash(f"OTP code sent. Check your email or authenticator app.", "info")
                return redirect(url_for("auth.verify_otp"))

            # Regular login without OTP
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Welcome back, {user.full_name}!", "success")
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("user.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    """Verify OTP code (either from authenticator or manual entry)."""
    pending_user_id = session.get("pending_user_id")
    
    if not pending_user_id:
        flash("Session expired. Please log in again.", "danger")
        return redirect(url_for("auth.login"))
    
    user = User.query.get(pending_user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.login"))
    
    if request.method == "POST":
        otp_code = request.form.get("otp_code", "").strip()
        use_backup = request.form.get("use_backup", False)
        
        if not otp_code:
            flash("OTP code is required.", "danger")
            return redirect(url_for("auth.verify_otp"))
        
        is_valid = False
        
        # Check if using backup code
        if use_backup and user.otp_backup_codes:
            backup_codes = user.otp_backup_codes.split(",")
            if otp_code in backup_codes:
                is_valid = True
                # Remove used backup code
                backup_codes.remove(otp_code)
                user.otp_backup_codes = ",".join(backup_codes)
        else:
            # Check TOTP
            if user.otp_secret and verify_otp_token(user.otp_secret, otp_code):
                is_valid = True
            # Check manual OTP
            elif (user.manual_otp_code == otp_code and 
                  user.manual_otp_expires_at and 
                  not is_otp_expired(user.manual_otp_expires_at)):
                is_valid = True
                # Clear used manual OTP
                user.manual_otp_code = None
                user.manual_otp_expires_at = None
        
        if is_valid:
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            db.session.commit()
            flash(f"Welcome back, {user.full_name}!", "success")
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("user.dashboard"))
        else:
            flash("Invalid OTP code.", "danger")
            return redirect(url_for("auth.verify_otp"))
    
    return render_template("verify-otp.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        role = request.form.get("role", "user")

        if not all([username, email, password, full_name]):
            flash("All required fields must be filled.", "danger")
            return redirect(url_for("auth.register"))

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "danger")
            return redirect(url_for("auth.register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("auth.register"))

        username_user = User.query.filter_by(username=username).first()
        email_user = User.query.filter_by(email=email).first()

        if username_user and email_user and username_user.id != email_user.id:
            flash("That username and email already belong to different accounts.", "danger")
            return redirect(url_for("auth.register"))

        existing_user = username_user or email_user
        if existing_user and existing_user.email_verified:
            if username_user:
                flash("Username already exists.", "danger")
            else:
                flash("Email already registered.", "danger")
            return redirect(url_for("auth.register"))

        if role not in VALID_ROLES:
            role = "user"

        if existing_user and not existing_user.email_verified:
            existing_user.username = username
            existing_user.email = email
            existing_user.full_name = full_name
            existing_user.phone = phone
            existing_user.role = role
            existing_user.set_password(password)
            db.session.commit()
            user = existing_user
            flash("We found your unverified account and updated it with the new details.", "info")
        else:
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                role=role,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

        try:
            if _smtp_configured():
                sent, _ = _send_verification_email(user)
                if sent:
                    flash("Registration successful! A verification email has been sent. Please check your inbox.", "success")
                else:
                    flash("Registration saved, but verification email could not be sent. Check SMTP settings or use the logged verification link.", "warning")
            else:
                user.email_verified = True
                db.session.commit()
                flash("Registration successful! Email verification is disabled in local mode, so your account is ready to use.", "success")
        except Exception as e:
            current_app.logger.error(f"Error sending verification email: {e}")
            flash("Registration saved, but there was an error sending the verification email.", "warning")

        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/auth0/login")
@auth_bp.route("/auth0/login/<provider>")
def login_with_auth0(provider=None):
    """Redirect to Auth0 login with optional social provider.

    Supported providers: google, facebook, github, microsoft, linkedin, twitter
    """
    from bloodbank.auth0_utils import oauth, get_connection_name

    # Build the redirect URL
    redirect_uri = current_app.config.get('AUTH0_CALLBACK_URL')

    # If provider is specified, add connection parameter
    kwargs = {'redirect_uri': redirect_uri}

    if provider:
        allowed_providers = ['google', 'facebook', 'github', 'microsoft', 'linkedin', 'twitter']
        if provider in allowed_providers:
            # Use the proper Auth0 connection name (e.g., google-oauth2 for google)
            connection = get_connection_name(provider)
            kwargs['connection'] = connection
            session['auth0_provider'] = provider

    return oauth.auth0.authorize_redirect(**kwargs)


@auth_bp.route("/auth0/callback")
def auth0_callback():
    """Auth0 callback handler."""
    from bloodbank.auth0_utils import oauth
    from flask import current_app
    
    token = oauth.auth0.authorize_access_token()
    session["auth0_token"] = token
    
    # Get user info from Auth0
    user_info = get_auth0_user_info(token.get('access_token'))
    
    if not user_info:
        flash("Failed to get user information from Auth0.", "danger")
        return redirect(url_for("auth.login"))
    
    auth0_id = user_info.get('sub')
    email = user_info.get('email')
    name = user_info.get('name', '').split(' ')
    full_name = user_info.get('name', 'Auth0 User')
    
    # Check if user exists by Auth0 ID
    user = User.query.filter_by(auth0_id=auth0_id).first()
    
    if not user:
        # Check if email exists
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Create new user from Auth0
            username = email.split('@')[0]
            counter = 1
            base_username = username
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                auth0_id=auth0_id,
                role="user"
            )
            # Auth0 users don't have password
            user.set_password(auth0_id)  # Set dummy password
            db.session.add(user)
        else:
            # Link existing user to Auth0
            user.auth0_id = auth0_id
        
        db.session.commit()
    
    # Log in the user
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    
    flash(f"Welcome, {user.full_name}!", "success")
    if user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("user.dashboard"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("main.home"))


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    """Verify user's email using token."""
    try:
        serializer = URLSafeTimedSerializer(current_app.config.get("SECRET_KEY"))
        email = serializer.loads(token, salt="email-verify", max_age=3600)
    except SignatureExpired:
        flash("Verification link has expired.", "danger")
        return redirect(url_for("auth.login"))
    except BadSignature:
        flash("Invalid verification token.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.register"))

    user.email_verified = True
    db.session.commit()
    flash("Email verified successfully. Please log in.", "success")
    return redirect(url_for("auth.login"))

