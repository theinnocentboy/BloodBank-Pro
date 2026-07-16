from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify
from datetime import datetime
import pytz
from bloodbank.constants import BLOOD_GROUPS
from bloodbank.decorators import login_required, verified_required
from bloodbank.extensions import db
from bloodbank.models import Donor, User, DonationAppointment, DonationSlot
from bloodbank.routes.user import calculate_age

donor_bp = Blueprint("donor", __name__)

IST = pytz.timezone('Asia/Kolkata')

@donor_bp.route("/search-donors", methods=["GET", "POST"])
def search_donors():
    donors = []
    if request.method == "POST":
        blood_group = request.form.get("blood_group", "").strip()
        city = request.form.get("city", "").strip()

        query = Donor.query.filter_by(availability=True)
        if blood_group:
            query = query.filter_by(blood_group=blood_group)
        if city:
            query = query.filter(Donor.city.ilike(f"%{city}%"))
        donors = query.all()

        if not donors:
            flash("No available donors match your search.", "info")

    return render_template(
        "search-donors.html", donors=donors, blood_groups=BLOOD_GROUPS
    )


@donor_bp.route("/donor/list")
def donor_list():
    donors = Donor.query.filter_by(availability=True).all()
    return render_template("donor-list.html", donors=donors)


@donor_bp.route("/donor/register", methods=["GET", "POST"])
@login_required
@verified_required
def register_donor():
    user = db.session.get(User, session["user_id"])
    if not user:
        return redirect(url_for("auth.login"))

    existing = Donor.query.filter_by(user_id=user.id).first()
    if existing:
        flash("You are already registered as a donor.", "info")
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":
        # 1. Enforce DOB Existence before processing form
        if not user.dob:
            flash("Medical Policy: You must provide your Date of Birth in the Personal tab before registering as a donor.", "warning")
            return redirect(url_for("user.profile", tab="details"))

        # 2. Calculate Exact Age
        age = calculate_age(user.dob)

        # 3. Apply Clinical Age Restrictions
        if age < 18:
            flash(f"Clinical Restriction: You are {age} years old. Medical regulations require blood donors to be at least 18.", "danger")
            return redirect(url_for("user.profile", tab="details"))
            
        if age > 65:
            flash("Clinical Restriction: For cardiovascular safety, blood donation is restricted to individuals 65 years and younger.", "danger")
            return redirect(url_for("user.profile", tab="details"))

        # 4. Process Form Data
        blood_group = request.form.get("blood_group", "").strip()
        city = request.form.get("city", "").strip()

        if blood_group not in BLOOD_GROUPS or not city:
            flash("Blood group and city are required.", "danger")
            return redirect(url_for("donor.register_donor"))

        donor = Donor(user_id=user.id, blood_group=blood_group, city=city)
        db.session.add(donor)
        db.session.commit()
        
        flash("You are now registered as a donor.", "success")
        return redirect(url_for("user.dashboard"))

    return render_template("donor-register.html", blood_groups=BLOOD_GROUPS)

# --- NEW DYNAMIC SLOT API ---
@donor_bp.route("/api/get-available-slots/<date_str>", methods=["GET"])
@login_required
def get_available_slots(date_str):
    """API for the Donor UI to fetch ONLY unlocked slots for a specific date."""
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date'}), 400

    # Get all slots for this date that the Admin has NOT locked
    available_slots = DonationSlot.query.filter_by(
        date=query_date, 
        is_locked=False
    ).all()
    
    # Filter out slots that have reached maximum capacity
    valid_slots = []
    for slot in available_slots:
        current_bookings = slot.appointments.count()
        if current_bookings < slot.max_capacity:
            valid_slots.append({
                'slot_id': slot.id,
                'time': slot.time_string,
                'remaining': slot.max_capacity - current_bookings
            })
            
    return jsonify({'slots': valid_slots})


# --- UPDATED SECURE BOOKING ROUTE ---
@donor_bp.route("/donor/book-appointment", methods=["GET", "POST"])
@login_required
@verified_required
def book_appointment():
    """Donor-side endpoint to request a donation time slot."""
    user_id = session.get("user_id")
    donor = Donor.query.filter_by(user_id=user_id).first()
    
    if not donor:
        flash("You must register as a donor first.", "warning")
        return redirect(url_for("donor.register_donor"))

    if request.method == "POST":
        # We now expect a slot_id from the frontend instead of raw strings
        slot_id = request.form.get("slot_id")
        
        if not slot_id:
            flash("Please select a valid time slot.", "danger")
            return redirect(url_for("donor.book_appointment"))

        slot = db.session.get(DonationSlot, slot_id)
        
        # Security Check: Ensure slot exists, isn't locked by admin, and isn't full
        if not slot or slot.is_locked:
            flash("This slot is no longer available. Please choose another.", "danger")
            return redirect(url_for("donor.book_appointment"))
            
        if slot.appointments.count() >= slot.max_capacity:
            flash("This slot has reached maximum capacity.", "warning")
            return redirect(url_for("donor.book_appointment"))

        # Prevent duplicate pending appointments
        existing = DonationAppointment.query.filter_by(
            donor_id=donor.id, 
            status='scheduled'
        ).first()
        
        if existing:
            flash("You already have an appointment scheduled. Please wait for this to be processed.", "info")
            return redirect(url_for("user.dashboard"))

        # Save to database (Linked securely to the Admin's DonationSlot)
        new_appointment = DonationAppointment(
            donor_id=donor.id,
            slot_id=slot.id,                     
            appointment_date=slot.date,          
            time_slot=slot.time_string,          
            status='scheduled'
        )
        db.session.add(new_appointment)
        db.session.commit()
        
        flash("Appointment request submitted successfully!", "success")
        return redirect(url_for("user.dashboard"))
    
    today_str = datetime.now(IST).strftime('%Y-%m-%d')

    return render_template("donor-book.html", current_date = today_str)