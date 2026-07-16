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



auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not login_id or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("auth.login"))

        user = User.query.filter((User.username == login_id) | (User.email == login_id)).first()
        
        if user and user.check_password(password):
            
            # --- THE FIREWALL: Reject admins from the public login ---
            if user.is_admin or user.role == 'admin':
                flash("Administrators must authenticate through the secure Admin Portal.", "warning")
                return redirect(url_for("admin.admin_login"))

            # --- HARD GATE: Email Verification ---
            if not user.email_verified:
                otp_code = generate_manual_otp_code()
                user.email_otp_code = otp_code
                user.email_otp_expires_at = get_otp_expiry_time(300)
                db.session.commit()
                
                session["pending_user_id"] = user.id
                send_otp_email(user.email, otp_code)
                
                flash("You must verify your email before entering the app.", "warning")
                return redirect(url_for("auth.verify_email_gate"))

            # If OTP (TOTP/Authenticator) is enabled
            if user.otp_enabled:
                session["pending_user_id"] = user.id
                session["login_time"] = datetime.utcnow().isoformat()
                flash("OTP verification is enabled. Use your authenticator app or a backup code.", "info")
                return redirect(url_for("auth.verify_otp"))

            # --- FULL AUTHENTICATION ---
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Welcome back, {user.full_name}!", "success")
            
            # --- SOFT GATE NOTIFICATION: Phone ---
            if not getattr(user, 'phone_verified', False):
                flash("Please remember to verify your mobile number in your profile settings.", "info")
            
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
    
    user = db.session.get(User, pending_user_id)
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
        
        if use_backup and user.otp_backup_codes:
            backup_codes = user.otp_backup_codes.split(",")
            if otp_code in backup_codes:
                is_valid = True
                backup_codes.remove(otp_code)
                user.otp_backup_codes = ",".join(backup_codes)
        else:
            if user.otp_secret and verify_otp_token(user.otp_secret, otp_code):
                is_valid = True
        
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
        phone_input = request.form.get("phone", "").strip()
        role = request.form.get("role", "user")

        if not all([username, email, password, full_name, phone_input]):
            flash("All required fields must be filled.", "danger")
            return redirect(url_for("auth.register"))

        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("auth.register"))

        clean_phone = re.sub(r'\D', '', phone_input)
        if len(clean_phone) == 10:
            formatted_phone = f"+91{clean_phone}"
        elif len(clean_phone) == 12 and clean_phone.startswith("91"):
            formatted_phone = f"+{clean_phone}"
        else:
            flash("Please enter a valid 10-digit Indian mobile number.", "danger")
            return redirect(url_for("auth.register"))

        if len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"\d", password):
            flash("Password must be at least 8 characters, with 1 uppercase, 1 lowercase, and 1 number.", "danger")
            return redirect(url_for("auth.register"))

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "danger")
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
            existing_user.phone = formatted_phone
            existing_user.role = role
            existing_user.set_password(password)
            existing_user.has_local_password = True
            db.session.commit()
            user = existing_user
            flash("We found your unverified account and updated it with the new details.", "info")
        else:
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=formatted_phone,
                role=role,
                has_local_password=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

        # --- HARD GATE: Generate Email OTP ---
        otp_code = generate_manual_otp_code()
        user.email_otp_code = otp_code
        user.email_otp_expires_at = get_otp_expiry_time(300) 
        db.session.commit()
        
        session["pending_user_id"] = user.id
        send_otp_email(user.email, otp_code)
    
        flash("Registration successful! We've sent a 6-digit code to your email.", "info")
        return redirect(url_for("auth.verify_email_gate"))

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
    pending_user_id = session.get("pending_user_id")
    if not pending_user_id:
        flash("Session expired. Please log in again.", "danger")
        return redirect(url_for("auth.login"))
        
    user = db.session.get(User, pending_user_id)
    
    if request.method == "POST":
        entered_code = request.form.get("otp_code", "").strip()
        
        if user.email_otp_code == entered_code and user.email_otp_expires_at > datetime.utcnow():
            user.email_verified = True
            user.email_otp_code = None
            user.email_otp_expires_at = None
            db.session.commit()
            
            # Upgrade to full session!
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            
            flash("Email verified successfully! Welcome to BloodBank.", "success")
            return redirect(url_for("user.dashboard"))
        else:
            flash("Invalid or expired OTP code.", "danger")
            
    return render_template("verify-email.html", email=user.email)


@auth_bp.route("/resend-email-otp", methods=["POST", "GET"]) 
def resend_email_otp():
    pending_user_id = session.get("pending_user_id")
    if not pending_user_id:
        return redirect(url_for("auth.login"))
        
    user = db.session.get(User, pending_user_id)
    otp_code = generate_manual_otp_code()
    user.email_otp_code = otp_code
    user.email_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()
    
    send_otp_email(user.email, otp_code)
    flash("A fresh Email verification code has been sent.", "success")
    return redirect(url_for("auth.verify_email_gate"))


# ==========================================
# 2. PHONE VERIFICATION (The New Soft Gate)
# ==========================================
@auth_bp.route("/verify-phone/send", methods=["GET"])
def send_phone_verification():
    """Triggered from the dashboard/profile to send the SMS OTP."""
    user = db.session.get(User, session.get("user_id"))
    if not user or user.phone_verified:
        return redirect(url_for("user.dashboard"))
        
    otp_code = generate_manual_otp_code()
    user.phone_otp_code = otp_code
    user.phone_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()
    
    send_sms_otp(user.phone, otp_code)
    flash(f"An OTP has been sent to {user.phone}", "info")
    return redirect(url_for("auth.confirm_phone_otp"))


@auth_bp.route("/verify-phone/confirm", methods=["GET", "POST"])
def confirm_phone_otp():
    """Validates the SMS code from logged-in users."""
    user = db.session.get(User, session.get("user_id"))
    if not user:
        return redirect(url_for("auth.login"))
        
    if request.method == "POST":
        entered_code = request.form.get("otp_code", "").strip()
        if user.phone_otp_code == entered_code and user.phone_otp_expires_at > datetime.utcnow():
            user.phone_verified = True
            user.phone_otp_code = None
            user.phone_otp_expires_at = None
            db.session.commit()
            
            flash("Phone successfully verified!", "success")
            return redirect(url_for("user.dashboard")) 
        else:
            flash("Invalid or expired code.", "danger")
            
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
        email = request.form.get('email').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # --- THE RECOVERY FIX ---
            # We no longer block social users. If they lost Google access, 
            # we immediately generate a token so they can create a local password!
            
            token = get_reset_token(user)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # For local testing, print the link directly to your terminal console:
            send_real_email(user.email, reset_url)
            
        # Standard fallback notice to protect account privacy
        flash("If an account with that email exists, a password reset link has been sent.", "info")
        return redirect(url_for('auth.login'))
        
    return render_template('forgot-password.html')

@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
        
    user = verify_reset_token(token)
    if not user:
        flash("That is an invalid or expired token. Please request a new one.", "danger")
        return redirect(url_for('auth.forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not is_moderate_password(password):
            flash("Password must be at least 8 characters long and include an uppercase letter, a lowercase letter, and a number.", "danger")
            return redirect(url_for('auth.reset_password', token=token))
            
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for('auth.reset_password', token=token))
            
        user.set_password(password)
        user.has_local_password = True 
        db.session.commit()
        
        flash("Your password has been successfully updated! You can now log in.", "success")
        return redirect(url_for('auth.login'))
        
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