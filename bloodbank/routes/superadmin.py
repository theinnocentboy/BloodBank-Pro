from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash

from bloodbank.extensions import db
from bloodbank.models import User, Donor, BloodRequest, BloodInventory
from bloodbank.decorators import superadmin_required

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/superadmin")

@superadmin_bp.route("/global-dashboard")
@superadmin_required
def global_dashboard():
    """High-level system overview for the Super Administrator."""
    stats = {
        "total_users": User.query.count(),
        "total_admins": User.query.filter_by(role='admin').count(),
        "total_donors": Donor.query.count(),
        "total_requests": BloodRequest.query.count()
    }
    return render_template("superadmin-dashboard.html", stats=stats)

@superadmin_bp.route("/staff")
@superadmin_required
def manage_staff():
    """View all regular administrator accounts."""
    # Fetch only accounts that currently have admin privileges
    staff = User.query.filter_by(role='admin').order_by(User.created_at.desc()).all()
    return render_template("superadmin-staff.html", staff=staff)

@superadmin_bp.route("/staff/create", methods=["POST"])
@superadmin_required
def create_staff():
    """Secure endpoint for Super Admins to create new Admin accounts."""
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password")

    if not all([username, email, full_name, password]):
        flash("All fields are required to create a staff account.", "danger")
        return redirect(url_for("superadmin.manage_staff"))

    # Prevent duplicate accounts
    existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        flash("An account with that username or email already exists.", "danger")
        return redirect(url_for("superadmin.manage_staff"))

    # Generate the Admin Account securely
    new_admin = User(
        username=username,
        email=email,
        full_name=full_name,
        password_hash=generate_password_hash(password),
        role="admin",
        email_verified=True 
    )
    
    db.session.add(new_admin)
    db.session.commit()
    
    flash(f"Administrator account for {full_name} created successfully.", "success")
    return redirect(url_for("superadmin.manage_staff"))

@superadmin_bp.route("/staff/<int:admin_id>/revoke", methods=["POST"])
@superadmin_required
def revoke_admin_access(admin_id):
    """Demote an administrator to a regular user."""
    # Safety Check: Prevent self-revocation
    if admin_id == session.get('user_id'):
        flash("Action Denied: You cannot revoke your own Super Administrator privileges.", "danger")
        return redirect(url_for("superadmin.manage_staff"))

    staff_member = User.query.get_or_404(admin_id)
    
    if staff_member.role != 'admin':
        flash("This user is not an active administrator.", "warning")
        return redirect(url_for("superadmin.manage_staff"))

    # Revoke privileges
    staff_member.role = 'user'
    db.session.commit()
    
    flash(f"Access revoked. {staff_member.username} is now a standard user.", "success")
    return redirect(url_for("superadmin.manage_staff"))

@superadmin_bp.route("/staff/<int:admin_id>/delete", methods=["POST"])
@superadmin_required
def delete_admin(admin_id):
    """Permanently delete an administrator account."""
    # Safety Check: Prevent self-deletion
    if admin_id == session.get('user_id'):
        flash("Action Denied: You cannot delete your own account.", "danger")
        return redirect(url_for("superadmin.manage_staff"))

    staff_member = User.query.get_or_404(admin_id)
    
    db.session.delete(staff_member)
    db.session.commit()
    
    flash(f"Administrator account {staff_member.username} permanently deleted.", "success")
    return redirect(url_for("superadmin.manage_staff"))

@superadmin_bp.route("/accounts")
@superadmin_required
def all_accounts():
    """Global directory of every registered account (Donors & Admins)."""
    # Fetch all users, newest first
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("superadmin-accounts.html", users=users)

@superadmin_bp.route("/accounts/<int:user_id>/delete", methods=["POST"])
@superadmin_required
def delete_global_account(user_id):
    """Ultimate authority to delete any user account in the system."""
    if user_id == session.get('user_id'):
        flash("Action Denied: You cannot delete your active session.", "danger")
        return redirect(url_for("superadmin.all_accounts"))

    user = User.query.get_or_404(user_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f"Account '{username}' has been permanently purged from the system.", "success")
    return redirect(url_for("superadmin.all_accounts"))

@superadmin_bp.route("/donors")
@superadmin_required
def all_donors():
    """Global view of all registered medical donors."""
    donors = Donor.query.all()
    return render_template("superadmin-donors.html", donors=donors)

@superadmin_bp.route("/requests")
@superadmin_required
def all_requests():
    """Global view of all blood requisition requests across the system."""
    requests_list = BloodRequest.query.order_by(BloodRequest.created_at.desc()).all()
    return render_template("superadmin-requests.html", requests=requests_list)

@superadmin_bp.route("/logout")
def logout():
    """Destroys the session and logs the Super Admin out."""
    session.clear()
    flash("Secure session terminated. You have been logged out.", "success")
    return redirect(url_for("admin.admin_login"))