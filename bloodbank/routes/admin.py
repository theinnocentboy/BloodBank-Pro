import os
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for, current_app, send_from_directory

from bloodbank.constants import BLOOD_GROUPS
from bloodbank.decorators import admin_required
from bloodbank.extensions import db
from bloodbank.models import BloodInventory, BloodRequest, Donor, User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    inventory = BloodInventory.query.order_by(BloodInventory.blood_group).all()
    recent_requests = (
        BloodRequest.query.order_by(BloodRequest.created_at.desc()).limit(5).all()
    )

    stats = {
        "total_users": User.query.count(),
        "total_donors": Donor.query.count(),
        "total_requests": BloodRequest.query.count(),
        "pending_requests": BloodRequest.query.filter_by(status="pending").count(),
        "blood_groups": BLOOD_GROUPS,
    }

    return render_template(
        "admin-dashboard.html",
        stats=stats,
        inventory=inventory,
        recent_requests=recent_requests,
    )


@admin_bp.route("/users")
@admin_required
def users():
    users_list = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin-users.html", users=users_list)


@admin_bp.route("/donors")
@admin_required
def donors():
    donors_list = Donor.query.all()
    return render_template("admin-donors.html", donors=donors_list)


@admin_bp.route("/requests")
@admin_required
def requests():
    requests_list = BloodRequest.query.order_by(BloodRequest.created_at.desc()).all()
    return render_template("admin-requests.html", requests=requests_list)


@admin_bp.route('/requests/approve/<int:req_id>', methods=['POST'])
@admin_required  
def approve_request(req_id):
    blood_req = BloodRequest.query.get_or_404(req_id)
    
    # Check if the document was verified first
    if not blood_req.is_verified:
        flash('You must verify the hospital requisition document before approving this request.', 'warning')
        return redirect(url_for('admin.requests'))
        
    # Query BloodInventory instead of Inventory
    inventory = BloodInventory.query.filter_by(blood_group=blood_req.blood_group).first()
    
    if not inventory or inventory.units < blood_req.quantity:
        flash(f'Insufficient stock for {blood_req.blood_group}.', 'danger')
        return redirect(url_for('admin.requests'))
        
    # Deduct stock and approve
    inventory.units -= blood_req.quantity
    blood_req.status = 'approved'
    db.session.commit()
    
    flash('Request approved and inventory deducted.', 'success')
    return redirect(url_for('admin.requests'))


@admin_bp.route("/request/<int:req_id>/reject", methods=["POST"])
@admin_required
def reject_request(req_id):
    blood_req = db.get_or_404(BloodRequest, req_id)
    if blood_req.status == "pending":
        blood_req.status = "rejected"
        db.session.commit()
        flash("Request rejected.", "success")
    else:
        flash("This request has already been processed.", "warning")
    return redirect(url_for("admin.requests"))


@admin_bp.route("/inventory")
@admin_required
def inventory():
    inventory_list = BloodInventory.query.order_by(BloodInventory.blood_group).all()
    return render_template("admin-inventory.html", inventory=inventory_list)


@admin_bp.route("/inventory/update/<int:inv_id>", methods=["POST"])
@admin_required
def update_inventory(inv_id):
    item = db.get_or_404(BloodInventory, inv_id)
    try:
        units = int(request.form.get("units", 0))
        if units < 0:
            raise ValueError
    except (TypeError, ValueError):
        flash("Units must be a non-negative number.", "danger")
        return redirect(url_for("admin.inventory"))

    item.units = units
    item.last_updated = datetime.utcnow()
    db.session.commit()
    flash(f"{item.blood_group} inventory updated.", "success")
    return redirect(url_for("admin.inventory"))


@admin_bp.route("/api/inventory-stats")
@admin_required
def inventory_stats():
    inventory = BloodInventory.query.order_by(BloodInventory.blood_group).all()
    return jsonify(
        {
            "blood_groups": [item.blood_group for item in inventory],
            "units": [item.units for item in inventory],
        }
    )


# --- NEW VERIFICATION PIPELINE ROUTES ---

@admin_bp.route('/document/<filename>')
@admin_required
def serve_document(filename):
    upload_folder = current_app.config.get(
        'UPLOAD_FOLDER', 
        os.path.join(current_app.instance_path, 'uploads', 'requisitions')
    )
    return send_from_directory(upload_folder, filename)


@admin_bp.route('/requests/verify/<int:req_id>', methods=['POST'])
@admin_required
def verify_request(req_id):
    blood_req = BloodRequest.query.get_or_404(req_id)
    
    if not blood_req.requisition_doc:
        flash('Cannot verify: No document was uploaded with this request.', 'danger')
        return redirect(url_for('admin.requests'))

    blood_req.is_verified = True
    db.session.commit()
    
    flash(f'Request #{req_id} has been verified successfully. You can now approve stock release.', 'success')
    return redirect(url_for('admin.requests'))