import os
from datetime import datetime, timedelta
import uuid
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for, current_app, send_from_directory
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from bloodbank.constants import BLOOD_GROUPS
from bloodbank.decorators import admin_required
from bloodbank.extensions import db
from bloodbank.models import BloodInventory, BloodRequest, Donor, User, DonationAppointment, DonationRecord, MedicalScreening
from bloodbank.services.donation_service import DonationService, ScreeningService # Adjust import path if needed
from bloodbank.models import DonationSlot
import pytz

IST = pytz.timezone('Asia/Kolkata')

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# --- DEDICATED ADMIN AUTHENTICATION ---
@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    # 1. Route already-logged-in staff to their correct dashboards
    if session.get('user_id'):
        if session.get('role') == 'superadmin':
            return redirect(url_for('superadmin.global_dashboard'))
        elif session.get('role') == 'admin':
            return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip() 
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        
        # 2. Exact Error Diagnosing
        if not user:
            flash('Account not found in the system.', 'danger')
        elif not user.check_password(password):
            flash('Incorrect password.', 'danger')
        
        # NEW: Security Ban Check
        # Uses getattr to safely default to True (active) if the column doesn't exist yet
        elif not getattr(user, 'is_active', True):
            flash('This account has been disabled by an administrator. Please contact support.', 'danger')
            
        elif getattr(user, 'role', '') not in ['admin', 'superadmin']:
            flash('Access Denied: This account lacks administrator privileges.', 'warning')
        else:
            # 3. Dynamic Login Success
            session.clear() 
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role  
            
            flash('Secure connection established.', 'success')
            
            # 4. Smart Routing (Updated to global_dashboard)
            if user.role == 'superadmin':
                return redirect(url_for('superadmin.global_dashboard'))
            else:
                return redirect(url_for('admin.dashboard'))

    return render_template('admin-login.html')


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    inventory = BloodInventory.query.order_by(BloodInventory.blood_group).all()
    recent_requests = (
        BloodRequest.query.order_by(BloodRequest.created_at.desc()).limit(5).all()
    )

    stats = {
        "total_users": User.query.filter(User.role.in_(["user", "recipient", "both"])).count(),
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
    users_list = User.query.filter(
        User.role.notin_(['admin', 'superadmin'])
    ).order_by(User.created_at.desc()).all()
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
    item.last_updated = datetime.now()
    db.session.commit()
    flash(f"{item.blood_group} inventory updated.", "success")
    return redirect(url_for("admin.inventory"))


@admin_bp.route("/api/inventory-stats")
@admin_required
def inventory_stats():
    inventory = BloodInventory.query.order_by(BloodInventory.blood_groupcre).all()
    return jsonify(
        {
            "blood_groups": [item.blood_group for item in inventory],
            "units": [item.units for item in inventory],
        }
    )


# --- VERIFICATION PIPELINE ROUTES ---

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

    # Update BOTH the boolean flag for the backend logic AND the status string for the UI
    blood_req.is_verified = True
    blood_req.status = 'verified' 
    db.session.commit()
    
    flash(f'Request #{req_id} has been verified successfully. You can now approve stock release.', 'success')
    return redirect(url_for('admin.requests'))


# --- NEW PHYSICAL FACILITY & APPOINTMENT ROUTES ---

@admin_bp.route('/api/appointments/today', methods=['GET'])
@admin_required
def get_todays_appointments():
    """Fetch all donation appointments scheduled for today."""
    today = datetime.now(IST).date()
    
    # Optimized query: Only pull today's records
    appointments = DonationAppointment.query.filter(
        db.func.date(DonationAppointment.appointment_date) == today
    ).order_by(DonationAppointment.time_slot.asc()).all()
    
    data = []
    for appt in appointments:
        data.append({
            'appointment_id': appt.id,
            'donor_name': appt.donor.user.full_name,
            'blood_group': appt.donor.blood_group,
            'time_slot': appt.time_slot,
            'status': appt.status
        })
        
    return jsonify({
        'success': True,
        'date': today.strftime("%Y-%m-%d"),
        'total_appointments': len(data),
        'appointments': data
    }), 200


@admin_bp.route('/api/appointments/<int:appointment_id>/process', methods=['POST'])
@admin_required
def process_donor_vitals(appointment_id):
    """Process medical screening and log the physical blood bag."""
    data = request.get_json()
    
    # Extract current logged-in admin user ID from session
    admin_id = session.get('user_id', 1) 
    action = data.get('action', 'screen')

    if action == 'defer':
        appt = DonationAppointment.query.get_or_404(appointment_id)
        appt.status = 'deferred'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Donor officially deferred. Removed from queue.'}), 200
    # Extract vitals from the incoming JSON request
    vitals = {
        'weight_kg': float(data.get('weight_kg', 0)),
        'blood_pressure': data.get('blood_pressure', ''),
        'hemoglobin_level': float(data.get('hemoglobin_level', 0)),
        'temperature_c': float(data.get('temperature_c', 0))
    }
    
    if action != 'override':
        is_passed, message, status = ScreeningService.validate_vitals(vitals)
        if not is_passed:
            return jsonify({'success': False, 'message': message, 'status': status}), 400
    
    # Hand off to the optimized service layer
    result = DonationService.process_walk_in(appointment_id, admin_id, vitals)
    
    status_code = 200 if result['success'] else 400
    return jsonify(result), status_code

@admin_bp.route("/slots")
@admin_required
def manage_slots():
    """Render the Admin UI to manage facility time slots."""
    # Fetch all slots, ordered by date and time
    slots = DonationSlot.query.order_by(DonationSlot.date.desc(), DonationSlot.time_string.asc()).all()
    today_str = datetime.now(IST).strftime('%Y-%m-%d')
    return render_template("admin-slots.html", slots=slots, current_date = today_str)

@admin_bp.route('/api/inventory/expiring-soon', methods=['GET'])
@admin_required
def get_expiring_inventory():
    """Find all blood bags expiring within the next 7 days."""
    today = datetime.now(IST)
    warning_date = today + timedelta(days=7)
    
    # Query for available blood that is expiring soon
    expiring_records = DonationRecord.query.filter(
        DonationRecord.status == 'available',
        DonationRecord.expiry_date <= warning_date
    ).order_by(DonationRecord.expiry_date.asc()).all()
    
    data = []
    for record in expiring_records:
        days_left = (record.expiry_date - today).days
        data.append({
            'serial_number': record.unit_serial_number,
            'blood_group': record.donor.blood_group,
            'component': record.blood_component,
            'expiry_date': record.expiry_date.strftime("%Y-%m-%d"),
            'days_remaining': days_left,
            'urgency': 'CRITICAL' if days_left <= 2 else 'WARNING'
        })
        
    return jsonify({
        'success': True,
        'expiring_count': len(data),
        'records': data
    }), 200

@admin_bp.route('/api/slots/manage', methods=['POST'])
@admin_required
def toggle_slot_status():
    """Admin route to manually lock or unlock a time slot."""
    data = request.get_json()
    slot_id = data.get('slot_id')
    action = data.get('action') # 'lock' or 'unlock'
    
    slot = db.session.get(DonationSlot, slot_id)
    if not slot:
        return jsonify({'success': False, 'message': 'Slot not found'}), 404
        
    if action == 'lock':
        slot.is_locked = True
    elif action == 'unlock':
        slot.is_locked = False
        
    db.session.commit()
    return jsonify({
        'success': True, 
        'message': f"Slot {slot.time_string} is now {'Locked' if slot.is_locked else 'Available'}."
    })

@admin_bp.route("/slots/create", methods=["POST"])
@admin_required
def create_slot():
    """Admin route to generate a new available time slot."""
    date_str = request.form.get("date")
    capacity = request.form.get("capacity", type=int)
    time_option = request.form.get("time_string") # This gets the dropdown value
    
    # 1. Date Validation
    try:
        slot_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash("Invalid date format.", "danger")
        return redirect(url_for("admin.manage_slots"))

    # 2. Logic to determine final time_string
    if time_option == "custom-slot":
        start_time = request.form.get("custom_start")
        end_time = request.form.get("custom_end")
        
        if not start_time or not end_time:
            flash("Please provide start and end times for the custom slot.", "danger")
            return redirect(url_for("admin.manage_slots"))
            
        # Convert 24h input format to 12h AM/PM string
        try:
            start_dt = datetime.strptime(start_time, "%H:%M")
            end_dt = datetime.strptime(end_time, "%H:%M")
            time_string = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"
        except ValueError:
            flash("Invalid time format provided.", "danger")
            return redirect(url_for("admin.manage_slots"))
    else:
        # Use the standard dropdown selection
        time_string = time_option

    # 3. Final Validation
    if not time_string or not capacity or capacity < 1:
        flash("Please provide a valid time window and capacity.", "danger")
        return redirect(url_for("admin.manage_slots"))

    # 4. Prevent duplicate slots for the exact same time on the same day
    existing = DonationSlot.query.filter_by(date=slot_date, time_string=time_string).first()
    if existing:
        flash(f"A slot for {time_string} already exists on {date_str}.", "warning")
        return redirect(url_for("admin.manage_slots"))

    # 5. Create and save new slot
    new_slot = DonationSlot(
        date=slot_date,
        time_string=time_string,
        max_capacity=capacity,
        is_locked=False 
    )
    db.session.add(new_slot)
    db.session.commit()
    
    flash("New facility slot generated successfully!", "success")
    return redirect(url_for("admin.manage_slots"))

@admin_bp.route('/api/appointments/upcoming')
@admin_required
def get_upcoming_appointments():
    """Fetch all scheduled appointments strictly after today."""
    today = datetime.now(IST).date()
    
    upcoming = DonationAppointment.query.filter(
        DonationAppointment.appointment_date > today,
        DonationAppointment.status == 'scheduled'
    ).order_by(
        DonationAppointment.appointment_date.asc(),
        DonationAppointment.time_slot.asc()
    ).limit(10).all() # Limit to next 10 for dashboard cleanliness
    
    data = [{
        'appointment_id': appt.id,
        'donor_name': appt.donor.user.full_name,
        'blood_group': appt.donor.blood_group,
        'date': appt.appointment_date.strftime('%b %d, %Y'), # Includes the date!
        'time_slot': appt.time_slot,
        'status': appt.status
    } for appt in upcoming]
    
    return jsonify({'appointments': data})

@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    """Allows Admin to Ban/Unban a user."""
    user = User.query.get_or_404(user_id)
    
    # Toggle the status
    user.is_active = not user.is_active
    db.session.commit()
    
    status = "enabled" if user.is_active else "banned"
    flash(f"User @{user.username} has been {status}.", "success")
    return redirect(url_for("admin.users"))

@admin_bp.route("/profile", methods=["GET", "POST"])
@admin_required
def profile():
    admin_user = db.session.get(User, session.get("user_id"))
    
    if request.method == "POST":
        action = request.form.get("action", "details")
        
        if action == "details":
            return _update_admin_profile(admin_user)
        if action == "update_avatar":
            return _update_admin_avatar(admin_user)
            
    return render_template("admin-profile.html", user=admin_user)


def _update_admin_profile(admin_user):
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip() or None
    gender = request.form.get("gender", "").strip()
    dob_raw = request.form.get("dob", "").strip()

    if not full_name or not email:
        flash("Full name and email are required.", "danger")
        return redirect(url_for("admin.profile", tab="details"))

    # Parse Date of Birth safely
    if dob_raw:
        try:
            admin_user.dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
        except ValueError:
            pass 

    admin_user.full_name = full_name
    admin_user.email = email
    admin_user.phone = phone
    admin_user.gender = gender if gender else None
    
    db.session.commit()
    flash("Admin profile updated successfully.", "success")
    return redirect(url_for("admin.profile", tab="details"))


def _update_admin_avatar(admin_user):
    if 'profile_pic' not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("admin.profile"))
        
    file = request.files['profile_pic']
    
    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for("admin.profile"))
        
    # Assuming you have an allowed_file function imported
    if file:
        original_filename = secure_filename(file.filename)
        unique_filename = f"admin_{admin_user.id}_{uuid.uuid4().hex[:8]}_{original_filename}"
        
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        admin_user.profile_pic = unique_filename
        db.session.commit()
        flash("Admin profile picture updated successfully!", "success")
        
    return redirect(url_for("admin.profile"))