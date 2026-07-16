import os
import uuid
from werkzeug.utils import secure_filename
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from datetime import datetime
from bloodbank.constants import BLOOD_GROUPS, URGENCY_LEVELS
from bloodbank.sms_utils import send_sms_otp
from bloodbank.otp_utils import generate_manual_otp_code, get_otp_expiry_time
from bloodbank.decorators import login_required, verified_required
from bloodbank.extensions import db
from bloodbank.models import BloodRequest, Donor, User  
from datetime import datetime, date
import re
from bloodbank.services.donor_service import update_donor_profile
from bloodbank.services.user_service import (
    change_password as user_change_password,
    confirm_phone_otp as user_confirm_phone_otp,
    send_phone_verification as user_send_phone_verification,
    set_auth0_password as user_set_auth0_password,
    submit_blood_request,
    update_avatar as user_update_avatar,
    update_profile_details as user_update_profile_details,
)

user_bp = Blueprint("user", __name__)

ROLE_LABELS = {
    "admin": "Administrator",
    "donor": "Donor",
    "recipient": "Recipient",
    "both": "Donor & Recipient",
    "user": "User",
}

def allowed_file(filename):
    """Helper function to validate allowed file extensions."""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'pdf', 'png', 'jpg', 'jpeg'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def _get_current_user():
    return db.session.get(User, session.get("user_id"))


@user_bp.route("/dashboard")
@login_required
def dashboard():
    user = _get_current_user()
    if not user:
        session.clear()
        flash("Session expired. Please log in again.", "warning")
        return redirect(url_for("auth.login"))

    requests = BloodRequest.query.filter_by(user_id=user.id).order_by(
        BloodRequest.created_at.desc()
    ).all()
    donor = Donor.query.filter_by(user_id=user.id).first()

    stats = {
        "total_requests": len(requests),
        "pending": sum(1 for r in requests if r.status == "pending"),
        "approved": sum(1 for r in requests if r.status == "approved"),
        "is_donor": donor is not None,
    }

    return render_template(
        "dashboard.html", user=user, stats=stats, donor=donor, requests=requests
    )


@user_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = _get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    donor = Donor.query.filter_by(user_id=user.id).first()

    if request.method == "POST":
        action = request.form.get("action", "details")

        if action == "details":
            result = user_update_profile_details(user.id, request.form, request.files)
            flash(result["message"], result["category"])
            return redirect(url_for("user.profile", tab="details"))
        if action == "password":
            result = user_change_password(
                user.id,
                request.form.get("current_password", ""),
                request.form.get("new_password", ""),
                request.form.get("confirm_password", ""),
            )
            flash(result["message"], result["category"])
            return redirect(url_for("user.profile", tab="security"))
        if action == "set_password":           # <-- ADD THIS
            result = user_set_auth0_password(
                user.id,
                request.form.get("new_password", ""),
                request.form.get("confirm_password", ""),
                session,
            )
            flash(result["message"], result["category"])
            return redirect(url_for("user.profile", tab="security"))
        if action == "donor":
            result = update_donor_profile(user.id, request.form)
            flash(result["message"], result["category"])
            return redirect(url_for("user.profile", tab="donor"))
        if action == "update_avatar":                # <-- ADD THIS
            result = user_update_avatar(user.id, request.files.get("profile_pic"))
            flash(result["message"], result["category"])
            return redirect(url_for("user.profile"))

        flash("Invalid form submission.", "danger")

    return render_template(
        "profile.html",
        user=user,
        donor=donor,
        blood_groups=BLOOD_GROUPS,
        role_label=ROLE_LABELS.get(user.role, user.role.title()),
    )


@user_bp.route("/verify-phone")
@login_required
def verify_phone_page():
    user = db.session.get(User, session["user_id"])
    if not user:
        return redirect(url_for("auth.login"))
    return render_template("verify-phone.html", phone=user.phone)


def _update_profile_details(user):
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip() or None
    gender = request.form.get("gender", "").strip()
    dob_raw = request.form.get("dob", "").strip()

    if not full_name or not email:
        flash("Full name and email are required.", "danger")
        return redirect(url_for("user.profile", tab="details"))

    existing = User.query.filter(User.email == email, User.id != user.id).first()
    if existing:
        flash("This email is already registered to another account.", "danger")
        return redirect(url_for("user.profile", tab="details"))

    # --- 1. Parse Date of Birth safely ---
    new_dob = None
    if dob_raw:
        try:
            new_dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for("user.profile", tab="details"))

        # --- PHASE 2: CLINICAL FIREWALL (For Existing Donors) ---
        donor = Donor.query.filter_by(user_id=user.id).first()
        if donor:
            age = calculate_age(new_dob)
            if age < 18 or age > 65:
                flash(f"Clinical Policy: As an active registered donor, your age must remain between 18 and 65 (calculated age: {age}). Update denied.", "danger")
                return redirect(url_for("user.profile", tab="details"))
        
        user.dob = new_dob

    # --- 2. Handle Profile Picture Upload ---
    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and file.filename != '' and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            unique_filename = f"avatar_{user.id}_{uuid.uuid4().hex[:8]}_{original_filename}"
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, unique_filename)
            file.save(file_path)
            user.profile_pic = unique_filename

    # --- 3. Save all other fields ---
    user.full_name = full_name
    user.email = email
    user.phone = phone
    user.gender = gender if gender else None
    
    db.session.commit()
    flash("Profile details updated successfully.", "success")
    return redirect(url_for("user.profile", tab="details"))

def _change_password(user):
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not all([current_password, new_password, confirm_password]):
        flash("All password fields are required.", "danger")
        return redirect(url_for("user.profile", tab="security"))

    if not user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("user.profile", tab="security"))

    if not is_moderate_password(new_password):
        flash("Password must be at least 8 characters long and include an uppercase letter, a lowercase letter, and a number.", "danger")
        return redirect(url_for("user.profile", tab="security"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("user.profile", tab="security"))

    if user.check_password(new_password):
        flash("New password must be different from your current password.", "danger")
        return redirect(url_for("user.profile", tab="security"))

    user.set_password(new_password)
    db.session.commit()
    flash("Password changed successfully.", "success")
    return redirect(url_for("user.profile", tab="security"))

@user_bp.route("/request-blood", methods=["GET", "POST"])
@login_required
@verified_required
def request_blood():
    if request.method == "POST":
        result = submit_blood_request(session["user_id"], request.form, request.files)
        flash(result["message"], result["category"])
        return redirect(url_for(result["redirect"]))

    return render_template("request-blood.html", blood_groups=BLOOD_GROUPS)

def is_moderate_password(password):
    """Checks if password is 8+ chars and contains an upper, lower, and digit."""
    if len(password) < 8: return False
    if not re.search(r"[A-Z]", password): return False
    if not re.search(r"[a-z]", password): return False
    if not re.search(r"\d", password): return False
    return True

@user_bp.route("/verify-phone/send", methods=["POST"])
@login_required
def send_phone_verification():
    result = user_send_phone_verification(session["user_id"])
    if result["message"]:
        flash(result["message"], result["category"])
    return redirect(url_for("user.verify_phone_page"))


@user_bp.route("/verify-phone/confirm", methods=["POST"])
@login_required
def confirm_phone():
    result = user_confirm_phone_otp(session["user_id"], request.form.get("otp_code", "").strip())
    flash(result["message"], result["category"])
    if result["success"]:
        return redirect(url_for("user.dashboard"))
    return redirect(url_for("user.verify_phone_page"))
    
def _update_avatar(user):
    result = user_update_avatar(user.id, request.files.get("profile_pic"))
    flash(result["message"], result["category"])
    return redirect(url_for("user.profile"))

def _set_auth0_password(user):
    result = user_set_auth0_password(user.id, request.form.get("new_password", ""), request.form.get("confirm_password", ""), session)
    flash(result["message"], result["category"])
    return redirect(url_for("user.profile", tab="security"))

def calculate_age(born):
    """Calculates exact age based on Date of Birth."""
    if not born:
        return 0
    today = date.today()
    # Subtract 1 year if the current month/day is before their birth month/day
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))