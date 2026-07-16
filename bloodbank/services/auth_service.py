"""Authentication business logic for BloodBank."""

from __future__ import annotations

import os
import re
from datetime import datetime

from flask import current_app, session, url_for
from itsdangerous import URLSafeTimedSerializer

from bloodbank.auth0_utils import get_auth0_user_info, is_auth0_enabled, oauth
from bloodbank.constants import VALID_ROLES
from bloodbank.email_utils import send_otp_email
from bloodbank.extensions import db
from bloodbank.models import User
from bloodbank.sms_utils import send_sms_otp
from bloodbank.utils import (
    generate_manual_otp_code,
    get_otp_expiry_time,
    is_moderate_password,
    send_real_email,
    use_backup_code,
    verify_otp_token,
)


def _response(success, message, category="info", redirect=None, render=None, context=None):
    return {
        "success": success,
        "message": message,
        "category": category,
        "redirect": redirect,
        "render": render,
        "context": context or {},
    }


def login_user(form, session_obj=session):
    login_id = form.get("username", "").strip()
    password = form.get("password", "")

    if not login_id or not password:
        return _response(False, "Username and password are required.", "danger", redirect="auth.login")

    user = User.query.filter((User.username == login_id) | (User.email == login_id)).first()
    if not user or not user.check_password(password):
        return _response(False, "Invalid username or password.", "danger", redirect="auth.login")

    if user.is_admin or user.role == "admin":
        return _response(False, "Administrators must authenticate through the secure Admin Portal.", "warning", redirect="admin.admin_login")

    if not user.email_verified:
        otp_code = generate_manual_otp_code()
        user.email_otp_code = otp_code
        user.email_otp_expires_at = get_otp_expiry_time(300)
        db.session.commit()
        session_obj["pending_user_id"] = user.id
        send_otp_email(user.email, otp_code)
        return _response(False, "You must verify your email before entering the app.", "warning", redirect="auth.verify_email_gate")

    if user.otp_enabled:
        session_obj["pending_user_id"] = user.id
        session_obj["login_time"] = datetime.utcnow().isoformat()
        return _response(False, "OTP verification is enabled. Use your authenticator app or a backup code.", "info", redirect="auth.verify_otp")

    session_obj.clear()
    session_obj["user_id"] = user.id
    session_obj["username"] = user.username
    session_obj["role"] = user.role

    flash_messages = [("success", f"Welcome back, {user.full_name}!")]
    if not getattr(user, "phone_verified", False):
        flash_messages.append(("info", "Please remember to verify your mobile number in your profile settings."))

    return {
        "success": True,
        "message": f"Welcome back, {user.full_name}!",
        "category": "success",
        "redirect": "user.dashboard",
        "flash_messages": flash_messages,
    }


def verify_otp(form, session_obj=session):
    pending_user_id = session_obj.get("pending_user_id")
    if not pending_user_id:
        return _response(False, "Session expired. Please log in again.", "danger", redirect="auth.login")

    user = db.session.get(User, pending_user_id)
    if not user:
        return _response(False, "User not found.", "danger", redirect="auth.login")

    otp_code = form.get("otp_code", "").strip()
    use_backup = form.get("use_backup", False)
    if not otp_code:
        return _response(False, "OTP code is required.", "danger", redirect="auth.verify_otp")

    is_valid = False
    if use_backup and user.otp_backup_codes:
        updated = use_backup_code(user.otp_backup_codes, otp_code)
        if updated is not None:
            is_valid = True
            user.otp_backup_codes = updated
    elif user.otp_secret and verify_otp_token(user.otp_secret, otp_code):
        is_valid = True

    if not is_valid:
        return _response(False, "Invalid OTP code.", "danger", redirect="auth.verify_otp")

    session_obj.clear()
    session_obj["user_id"] = user.id
    session_obj["username"] = user.username
    session_obj["role"] = user.role
    db.session.commit()

    redirect_target = "admin.dashboard" if user.is_admin else "user.dashboard"
    return {
        "success": True,
        "message": f"Welcome back, {user.full_name}!",
        "category": "success",
        "redirect": redirect_target,
        "flash_messages": [("success", f"Welcome back, {user.full_name}!")],
    }


def register_user(form, session_obj=session):
    username = form.get("username", "").strip()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    full_name = form.get("full_name", "").strip()
    phone_input = form.get("phone", "").strip()
    role = form.get("role", "user")

    if not all([username, email, password, full_name, phone_input]):
        return _response(False, "All required fields must be filled.", "danger", redirect="auth.register")

    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
        return _response(False, "Please enter a valid email address.", "danger", redirect="auth.register")

    clean_phone = re.sub(r"\D", "", phone_input)
    if len(clean_phone) == 10:
        formatted_phone = f"+91{clean_phone}"
    elif len(clean_phone) == 12 and clean_phone.startswith("91"):
        formatted_phone = f"+{clean_phone}"
    else:
        return _response(False, "Please enter a valid 10-digit Indian mobile number.", "danger", redirect="auth.register")

    if not is_moderate_password(password):
        return _response(False, "Password must be at least 8 characters, with 1 uppercase, 1 lowercase, and 1 number.", "danger", redirect="auth.register")

    if len(username) < 3:
        return _response(False, "Username must be at least 3 characters.", "danger", redirect="auth.register")

    username_user = User.query.filter_by(username=username).first()
    email_user = User.query.filter_by(email=email).first()

    if username_user and email_user and username_user.id != email_user.id:
        return _response(False, "That username and email already belong to different accounts.", "danger", redirect="auth.register")

    existing_user = username_user or email_user
    if existing_user and existing_user.email_verified:
        if username_user:
            return _response(False, "Username already exists.", "danger", redirect="auth.register")
        return _response(False, "Email already registered.", "danger", redirect="auth.register")

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
        flash_messages = [("info", "We found your unverified account and updated it with the new details.")]
    else:
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            phone=formatted_phone,
            role=role,
            has_local_password=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash_messages = []

    otp_code = generate_manual_otp_code()
    user.email_otp_code = otp_code
    user.email_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()

    session_obj["pending_user_id"] = user.id
    send_otp_email(user.email, otp_code)
    flash_messages.append(("info", "Registration successful! We've sent a 6-digit code to your email."))
    return {
        "success": True,
        "message": "Registration successful! We've sent a 6-digit code to your email.",
        "category": "info",
        "redirect": "auth.verify_email_gate",
        "flash_messages": flash_messages,
    }


def verify_email_gate(form, session_obj=session):
    pending_user_id = session_obj.get("pending_user_id")
    if not pending_user_id:
        return _response(False, "Session expired. Please log in again.", "danger", redirect="auth.login")

    user = db.session.get(User, pending_user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "danger", redirect="auth.login")

    entered_code = form.get("otp_code", "").strip()
    if user.email_otp_code == entered_code and user.email_otp_expires_at > datetime.utcnow():
        user.email_verified = True
        user.email_otp_code = None
        user.email_otp_expires_at = None
        db.session.commit()
        session_obj.clear()
        session_obj["user_id"] = user.id
        session_obj["username"] = user.username
        session_obj["role"] = user.role
        return _response(True, "Email verified successfully! Welcome to BloodBank.", "success", redirect="user.dashboard")

    return _response(False, "Invalid or expired OTP code.", "danger", render="verify-email.html", context={"email": user.email})


def resend_email_otp(session_obj=session):
    pending_user_id = session_obj.get("pending_user_id")
    if not pending_user_id:
        return _response(False, "Session expired. Please log in again.", "danger", redirect="auth.login")

    user = db.session.get(User, pending_user_id)
    otp_code = generate_manual_otp_code()
    user.email_otp_code = otp_code
    user.email_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()
    send_otp_email(user.email, otp_code)
    return _response(True, "A fresh Email verification code has been sent.", "success", redirect="auth.verify_email_gate")


def send_phone_verification(session_obj=session):
    user = db.session.get(User, session_obj.get("user_id"))
    if not user or user.phone_verified:
        return _response(True, "", "info", redirect="user.dashboard")

    otp_code = generate_manual_otp_code()
    user.phone_otp_code = otp_code
    user.phone_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()
    send_sms_otp(user.phone, otp_code)
    return _response(True, f"An OTP has been sent to {user.phone}", "info", redirect="auth.confirm_phone_otp")


def confirm_phone_otp(form, session_obj=session):
    user = db.session.get(User, session_obj.get("user_id"))
    if not user:
        return _response(False, "Session expired. Please log in again.", "danger", redirect="auth.login")

    entered_code = form.get("otp_code", "").strip()
    if user.phone_otp_code == entered_code and user.phone_otp_expires_at > datetime.utcnow():
        user.phone_verified = True
        user.phone_otp_code = None
        user.phone_otp_expires_at = None
        db.session.commit()
        return _response(True, "Phone successfully verified!", "success", redirect="user.dashboard")

    return _response(False, "Invalid or expired code.", "danger", render="verify-phone.html", context={"phone": user.phone})


def get_reset_token(user, expires_sec=1800):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps({"user_id": user.id}, salt="password-reset-salt")


def verify_reset_token(token, expires_sec=1800):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        user_id = serializer.loads(token, salt="password-reset-salt", max_age=expires_sec)["user_id"]
    except Exception:
        return None
    return db.session.get(User, user_id)


def forgot_password(email):
    user = User.query.filter_by(email=email).first()
    if user:
        token = get_reset_token(user)
        reset_url = url_for("auth.reset_password", token=token, _external=True)
        send_real_email(user.email, reset_url)
    return _response(True, "If an account with that email exists, a password reset link has been sent.", "info", redirect="auth.login")


def reset_password(token, form):
    user = verify_reset_token(token)
    if not user:
        return _response(False, "That is an invalid or expired token. Please request a new one.", "danger", redirect="auth.forgot_password")

    password = form.get("password")
    confirm_password = form.get("confirm_password")
    if not is_moderate_password(password):
        return _response(False, "Password must be at least 8 characters long and include an uppercase letter, a lowercase letter, and a number.", "danger", redirect="auth.reset_password")

    if password != confirm_password:
        return _response(False, "Passwords do not match.", "danger", redirect="auth.reset_password")

    user.set_password(password)
    user.has_local_password = True
    db.session.commit()
    return _response(True, "Your password has been successfully updated! You can now log in.", "success", redirect="auth.login")