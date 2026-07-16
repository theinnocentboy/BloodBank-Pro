"""User-facing business logic for BloodBank."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

from flask import current_app, session
from werkzeug.utils import secure_filename

from bloodbank.extensions import db
from bloodbank.models import BloodRequest, Donor, User
from bloodbank.sms_utils import send_sms_otp
from bloodbank.utils import (
    allowed_file,
    calculate_age,
    generate_manual_otp_code,
    get_otp_expiry_time,
    is_moderate_password,
)


def _response(success, message, category="info", redirect=None, render=None, context=None, flash_messages=None):
    return {
        "success": success,
        "message": message,
        "category": category,
        "redirect": redirect,
        "render": render,
        "context": context or {},
        "flash_messages": flash_messages or ([(category, message)] if message else []),
    }


def _s3_bucket_name():
    return os.environ.get("S3_BUCKET_NAME", "").strip()


def _s3_region():
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def _upload_to_storage(file_storage, *, subfolder, prefix, local_folder, use_public_url=False):
    if not file_storage or not file_storage.filename:
        return None

    if not allowed_file(file_storage.filename):
        return None

    original_filename = secure_filename(file_storage.filename)
    unique_filename = f"{prefix}_{uuid.uuid4().hex[:8]}_{original_filename}"
    bucket_name = _s3_bucket_name()

    if bucket_name:
        import boto3

        key = f"{subfolder}/{unique_filename}".replace("//", "/")
        file_storage.stream.seek(0)
        boto3.client("s3", region_name=_s3_region()).upload_fileobj(
            file_storage.stream,
            bucket_name,
            key,
            ExtraArgs={"ContentType": file_storage.mimetype or "application/octet-stream"},
        )

        if use_public_url:
            region = _s3_region()
            if region == "us-east-1":
                return f"https://{bucket_name}.s3.amazonaws.com/{key}"
            return f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}"

        return unique_filename

    upload_folder = os.path.join(local_folder, subfolder)
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, unique_filename)
    file_storage.save(file_path)
    return unique_filename


def update_profile_details(user_id, form, files):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip()
    phone = form.get("phone", "").strip() or None
    gender = form.get("gender", "").strip()
    dob_raw = form.get("dob", "").strip()

    if not full_name or not email:
        return _response(False, "Full name and email are required.", "danger", redirect="user.profile")

    existing = User.query.filter(User.email == email, User.id != user.id).first()
    if existing:
        return _response(False, "This email is already registered to another account.", "danger", redirect="user.profile")

    if dob_raw:
        try:
            new_dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
        except ValueError:
            return _response(False, "Invalid date format.", "danger", redirect="user.profile")

        donor = Donor.query.filter_by(user_id=user.id).first()
        if donor:
            age = calculate_age(new_dob)
            if age < 18 or age > 65:
                return _response(
                    False,
                    f"Clinical Policy: As an active registered donor, your age must remain between 18 and 65 (calculated age: {age}). Update denied.",
                    "danger",
                    redirect="user.profile",
                )

        user.dob = new_dob

    file = files.get("profile_pic")
    if file and file.filename and allowed_file(file.filename):
        user.profile_pic = _upload_to_storage(
            file,
            subfolder="profiles",
            prefix=f"avatar_{user.id}",
            local_folder=os.path.join(current_app.root_path, "static", "uploads"),
            use_public_url=True,
        )

    user.full_name = full_name
    user.email = email
    user.phone = phone
    user.gender = gender if gender else None

    db.session.commit()
    return _response(True, "Profile details updated successfully.", "success", redirect="user.profile")


def change_password(user_id, current_password, new_password, confirm_password):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    if not all([current_password, new_password, confirm_password]):
        return _response(False, "All password fields are required.", "danger", redirect="user.profile")

    if not user.check_password(current_password):
        return _response(False, "Current password is incorrect.", "danger", redirect="user.profile")

    if not is_moderate_password(new_password):
        return _response(
            False,
            "Password must be at least 8 characters long and include an uppercase letter, a lowercase letter, and a number.",
            "danger",
            redirect="user.profile",
        )

    if new_password != confirm_password:
        return _response(False, "New password and confirmation do not match.", "danger", redirect="user.profile")

    if user.check_password(new_password):
        return _response(False, "New password must be different from your current password.", "danger", redirect="user.profile")

    user.set_password(new_password)
    db.session.commit()
    return _response(True, "Password changed successfully.", "success", redirect="user.profile")


def set_auth0_password(user_id, new_password, confirm_password, session_obj=session):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    if not is_moderate_password(new_password):
        return _response(
            False,
            "Password must be at least 8 characters long and include an uppercase letter, a lowercase letter, and a number.",
            "danger",
            redirect="user.profile",
        )

    if new_password != confirm_password:
        return _response(False, "New passwords do not match.", "danger", redirect="user.profile")

    user.set_password(new_password)
    user.has_local_password = True
    db.session.commit()
    session_obj["local_password_set"] = True
    return _response(
        True,
        "Local password set successfully! You can now log in using either Google or your email.",
        "success",
        redirect="user.profile",
    )


def update_avatar(user_id, file):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    if not file or not file.filename:
        return _response(False, "No file selected.", "danger", redirect="user.profile")

    if file and allowed_file(file.filename):
        user.profile_pic = _upload_to_storage(
            file,
            subfolder="profiles",
            prefix=f"avatar_{user.id}",
            local_folder=os.path.join(current_app.root_path, "static", "uploads"),
            use_public_url=True,
        )
        db.session.commit()
        return _response(True, "Profile picture updated successfully!", "success", redirect="user.profile")

    return _response(False, "Invalid file type. Please upload a JPG or PNG.", "danger", redirect="user.profile")


def submit_blood_request(user_id, form, files):
    blood_group = form.get("blood_group", "").strip()
    quantity_raw = form.get("quantity", "").strip()
    urgency = form.get("urgency", "normal").strip()
    reason = form.get("reason", "").strip()

    from bloodbank.constants import BLOOD_GROUPS, URGENCY_LEVELS

    if blood_group not in BLOOD_GROUPS:
        return _response(False, "Please select a valid blood group.", "danger", redirect="user.request_blood")

    if urgency not in URGENCY_LEVELS:
        urgency = "normal"

    if not reason:
        return _response(False, "Please provide a reason for the request.", "danger", redirect="user.request_blood")

    try:
        quantity = int(quantity_raw)
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _response(False, "Quantity must be a positive number.", "danger", redirect="user.request_blood")

    if "requisition_doc" not in files:
        return _response(False, "Doctor's requisition document is required.", "danger", redirect="user.request_blood")

    file = files["requisition_doc"]
    if file.filename == "":
        return _response(False, "No document selected for uploading.", "danger", redirect="user.request_blood")

    if not allowed_file(file.filename):
        return _response(False, "Invalid file type. Please upload a PDF, JPG, or PNG.", "danger", redirect="user.request_blood")

    unique_filename = _upload_to_storage(
        file,
        subfolder="requisitions",
        prefix=uuid.uuid4().hex,
        local_folder=current_app.config.get(
            "UPLOAD_FOLDER",
            os.path.join(current_app.instance_path, "uploads"),
        ),
        use_public_url=False,
    )

    blood_req = BloodRequest(
        user_id=user_id,
        blood_group=blood_group,
        quantity=quantity,
        urgency=urgency,
        reason=reason,
        requisition_doc=unique_filename,
        is_verified=False,
    )

    db.session.add(blood_req)
    db.session.commit()
    return _response(True, "Blood request submitted successfully. Awaiting admin verification.", "success", redirect="user.dashboard")


def send_phone_verification(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    if not user.phone:
        return _response(False, "Please update your profile with a valid phone number first.", "danger", redirect="user.profile")

    otp_code = generate_manual_otp_code()
    user.manual_otp_code = otp_code
    user.manual_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()

    if send_sms_otp(user.phone, otp_code):
        return _response(True, f"Verification code sent to {user.phone}", "success", redirect="user.verify_phone_page")

    return _response(False, "Failed to send SMS. Please try again later.", "danger", redirect="user.verify_phone_page")


def confirm_phone_otp(user_id, entered_code):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    if user.manual_otp_code == entered_code and user.manual_otp_expires_at > datetime.now():
        user.phone_verified = True
        user.manual_otp_code = None
        user.manual_otp_expires_at = None
        db.session.commit()
        return _response(True, "Phone number successfully verified! You now have full access.", "success", redirect="user.dashboard")

    return _response(False, "Invalid or expired OTP.", "danger", redirect="user.verify_phone_page")
