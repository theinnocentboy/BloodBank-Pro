import os
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime

from bloodbank.constants import VALID_ROLES
from bloodbank.extensions import db
from bloodbank.models import User
from bloodbank.otp_utils import (
    is_otp_expired,
    verify_otp_token
)
from bloodbank.auth0_utils import oauth, get_auth0_user_info, is_auth0_enabled

auth_bp = Blueprint("auth", __name__)


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
            if not user.email_verified:
                user.email_verified = True
                db.session.commit()
                flash("Your account is now active.", "info")

            # If OTP is enabled, redirect to OTP verification
            if user.otp_enabled:
                session["pending_user_id"] = user.id
                session["login_time"] = datetime.utcnow().isoformat()
                flash("OTP verification is enabled. Use your authenticator app or a backup code.", "info")
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

        user.email_verified = True
        db.session.commit()
        flash("Registration successful! You can now log in to your account.", "success")

        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/auth0/login")
@auth_bp.route("/auth0/login/<provider>")
def login_with_auth0(provider=None):
    """Redirect to Auth0 login with optional social provider."""
    if not is_auth0_enabled():
        flash("Auth0 integration is not configured. Please use the regular login.", "warning")
        return redirect(url_for("auth.login"))
    
    try:
        # Use explicitly configured callback URL to avoid mismatches
        callback_url = current_app.config.get('AUTH0_CALLBACK_URL')
        if not callback_url:
            callback_url = url_for("auth.auth0_callback", _external=True)
        
        auth0_client = oauth.create_client('auth0')
        
        # If a provider is specified, add connection parameter
        if provider:
            return auth0_client.authorize_redirect(
                redirect_uri=callback_url,
                connection=provider
            )
        else:
            return auth0_client.authorize_redirect(redirect_uri=callback_url)
    except Exception as e:
        current_app.logger.error(f"Auth0 login error: {e}")
        flash("Error connecting to Auth0. Please use the standard login.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth0/callback")
def auth0_callback():
    """Auth0 callback handler."""
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
        
        # Extract user info
        user_data = get_auth0_user_info(userinfo)
        email = user_data['email']
        full_name = user_data['full_name']
        auth0_id = user_data['auth0_id']
        
        # Find or create user
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Update existing user with Auth0 info
            user.full_name = full_name
            db.session.commit()
        else:
            # Create new user from Auth0 info
            # Generate a username from email
            username = email.split('@')[0]
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{email.split('@')[0]}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                email_verified=True,  # Auth0 verified emails
                role='user'
            )
            # Set a random password (Auth0 users won't use it)
            user.set_password(os.urandom(32).hex())
            db.session.add(user)
            db.session.commit()
        
        # Log in the user
        session.clear()
        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role
        session["auth0_id"] = auth0_id
        
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
    """Logout user and clear session."""
    auth0_id = session.get("auth0_id")
    session.clear()
    
    # If user logged in via Auth0, redirect to Auth0 logout URL
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

