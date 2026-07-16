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
            return _update_profile_details(user)
        if action == "password":
            return _change_password(user)
        if action == "set_password":           # <-- ADD THIS
            return _set_auth0_password(user)
        if action == "donor":
            return _update_donor_profile(user, donor)
        if action == "update_avatar":                # <-- ADD THIS
            return _update_avatar(user)

        flash("Invalid form submission.", "danger")

    return render_template(
        "profile.html",
        user=user,
        donor=donor,
        blood_groups=BLOOD_GROUPS,
        role_label=ROLE_LABELS.get(user.role, user.role.title()),
    )


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
        blood_group = request.form.get("blood_group", "").strip()
        quantity_raw = request.form.get("quantity", "").strip()
        urgency = request.form.get("urgency", "normal").strip()
        reason = request.form.get("reason", "").strip()

        # 1. Basic Form Validation
        if blood_group not in BLOOD_GROUPS:
            flash("Please select a valid blood group.", "danger")
            return redirect(url_for("user.request_blood"))

        if urgency not in URGENCY_LEVELS:
            urgency = "normal"

        if not reason:
            flash("Please provide a reason for the request.", "danger")
            return redirect(url_for("user.request_blood"))

        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            flash("Quantity must be a positive number.", "danger")
            return redirect(url_for("user.request_blood"))

        # 2. Requisition Document Handling
        if 'requisition_doc' not in request.files:
            flash("Doctor's requisition document is required.", "danger")
            return redirect(request.url)
            
        file = request.files['requisition_doc']
        
        if file.filename == '':
            flash("No document selected for uploading.", "danger")
            return redirect(request.url)

        unique_filename = None
        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
            
            # Use configured upload folder, or default to instance/uploads/requisitions
            upload_folder = current_app.config.get(
                'UPLOAD_FOLDER', 
                os.path.join(current_app.instance_path, 'uploads', 'requisitions')
            )
            
            # Ensure directory exists before saving
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, unique_filename)
            file.save(file_path)
        else:
            flash("Invalid file type. Please upload a PDF, JPG, or PNG.", "danger")
            return redirect(request.url)

        # 3. Create Database Record
        blood_req = BloodRequest(
            user_id=session["user_id"],
            blood_group=blood_group,
            quantity=quantity,
            urgency=urgency,
            reason=reason,
            requisition_doc=unique_filename,
            is_verified=False
        )
        
        db.session.add(blood_req)
        db.session.commit()
        
        flash("Blood request submitted successfully. Awaiting admin verification.", "success")
        return redirect(url_for("user.dashboard"))

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
    user = db.session.get(User, session["user_id"])
    
    if not user.phone:
        flash("Please update your profile with a valid phone number first.", "danger")
        return redirect(url_for("user.profile"))
        
    # 1. Generate 6-digit code and 5-min expiry
    otp_code = generate_manual_otp_code()
    user.manual_otp_code = otp_code
    user.manual_otp_expires_at = get_otp_expiry_time(300)
    db.session.commit()
    
    # 2. Fire the SMS
    if send_sms_otp(user.phone, otp_code):
        flash(f"Verification code sent to {user.phone}", "success")
    else:
        flash("Failed to send SMS. Please try again later.", "danger")
        
    return redirect(url_for("user.verify_phone_page")) # Redirect to the UI where they enter the code


@user_bp.route("/verify-phone/confirm", methods=["POST"])
@login_required
def confirm_phone():
    user = db.session.get(User, session["user_id"])
    entered_code = request.form.get("otp_code").strip()
    
    # Validate code and check expiry
    if user.manual_otp_code == entered_code and user.manual_otp_expires_at > datetime.now():
        user.phone_verified = True
        user.manual_otp_code = None  # Clear the code for security
        user.manual_otp_expires_at = None
        db.session.commit()
        
        flash("Phone number successfully verified! You now have full access.", "success")
        return redirect(url_for("user.dashboard"))
    else:
        flash("Invalid or expired OTP.", "danger")
        return redirect(url_for("user.verify_phone_page"))
    
def _update_avatar(user):
    if 'profile_pic' not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("user.profile"))
        
    file = request.files['profile_pic']
    
    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for("user.profile"))
        
    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        # Create a unique filename using UUID to prevent caching issues
        unique_filename = f"avatar_{user.id}_{uuid.uuid4().hex[:8]}_{original_filename}"
        
        # Ensure the directory exists in the static folder
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_folder, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        # Update database
        user.profile_pic = unique_filename
        db.session.commit()
        
        flash("Profile picture updated successfully!", "success")
    else:
        flash("Invalid file type. Please upload a JPG or PNG.", "danger")
        
    return redirect(url_for("user.profile"))

def _set_auth0_password(user):
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    
    # 1. Validation Checks
    if not is_moderate_password(new_password):
        flash("Password must be at least 8 characters long and include an uppercase letter, a lowercase letter, and a number.", "danger")
        return redirect(url_for("user.profile", tab="security"))
        
    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("user.profile", tab="security"))
        
    # 2. Save the new password
    user.set_password(new_password)

    user.has_local_password = True

    db.session.commit()
    session['local_password_set'] = True
    flash("Local password set successfully! You can now log in using either Google or your email.", "success")
    return redirect(url_for("user.profile", tab="security"))

def calculate_age(born):
    """Calculates exact age based on Date of Birth."""
    if not born:
        return 0
    today = date.today()
    # Subtract 1 year if the current month/day is before their birth month/day
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))