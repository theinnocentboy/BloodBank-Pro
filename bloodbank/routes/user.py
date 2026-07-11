import os
import uuid
from werkzeug.utils import secure_filename
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app

from bloodbank.constants import BLOOD_GROUPS, URGENCY_LEVELS
from bloodbank.decorators import login_required
from bloodbank.extensions import db
from bloodbank.models import BloodRequest, Donor, User

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
        if action == "donor":
            return _update_donor_profile(user, donor)

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

    if not full_name or not email:
        flash("Full name and email are required.", "danger")
        return redirect(url_for("user.profile", tab="details"))

    if len(full_name) < 2:
        flash("Full name must be at least 2 characters.", "danger")
        return redirect(url_for("user.profile", tab="details"))

    existing = User.query.filter(User.email == email, User.id != user.id).first()
    if existing:
        flash("This email is already registered to another account.", "danger")
        return redirect(url_for("user.profile", tab="details"))

    user.full_name = full_name
    user.email = email
    user.phone = phone
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

    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "danger")
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


def _update_donor_profile(user, donor):
    if not donor:
        flash("You are not registered as a donor.", "warning")
        return redirect(url_for("user.profile"))

    blood_group = request.form.get("blood_group", "").strip()
    city = request.form.get("city", "").strip()
    availability = request.form.get("availability") == "1"

    if blood_group not in BLOOD_GROUPS or not city:
        flash("Valid blood group and city are required.", "danger")
        return redirect(url_for("user.profile", tab="donor"))

    if len(city) < 2:
        flash("City name is too short.", "danger")
        return redirect(url_for("user.profile", tab="donor"))

    donor.blood_group = blood_group
    donor.city = city
    donor.availability = availability
    db.session.commit()
    flash("Donor profile updated successfully.", "success")
    return redirect(url_for("user.profile", tab="donor"))


@user_bp.route("/request-blood", methods=["GET", "POST"])
@login_required
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