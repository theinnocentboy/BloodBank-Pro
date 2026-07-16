from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify
from datetime import datetime
import pytz
from bloodbank.constants import BLOOD_GROUPS
from bloodbank.decorators import login_required, verified_required
from bloodbank.extensions import db
from bloodbank.models import Donor, User, DonationAppointment, DonationSlot
from bloodbank.services.donor_service import (
    book_appointment as donor_book_appointment,
    get_available_slots as donor_get_available_slots,
    list_available_donors,
    register_donor as donor_register,
    search_donors as donor_search,
)

donor_bp = Blueprint("donor", __name__)

IST = pytz.timezone('Asia/Kolkata')

@donor_bp.route("/search-donors", methods=["GET", "POST"])
def search_donors():
    donors = []
    if request.method == "POST":
        blood_group = request.form.get("blood_group", "").strip()
        city = request.form.get("city", "").strip()

        donors = donor_search(blood_group=blood_group, city=city)

        if not donors:
            flash("No available donors match your search.", "info")

    return render_template(
        "search-donors.html", donors=donors, blood_groups=BLOOD_GROUPS
    )


@donor_bp.route("/donor/list")
def donor_list():
    donors = list_available_donors()
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
        blood_group = request.form.get("blood_group", "").strip()
        city = request.form.get("city", "").strip()
        result = donor_register(user.id, blood_group, city)
        flash(result["message"], result["category"])
        return redirect(url_for(result["redirect"]))

    return render_template("donor-register.html", blood_groups=BLOOD_GROUPS)

# --- NEW DYNAMIC SLOT API ---
@donor_bp.route("/api/get-available-slots/<date_str>", methods=["GET"])
@login_required
def get_available_slots(date_str):
    """API for the Donor UI to fetch ONLY unlocked slots for a specific date."""
    payload, status_code = donor_get_available_slots(date_str)
    return jsonify(payload), status_code


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
        slot_id = request.form.get("slot_id")
        result = donor_book_appointment(user_id, slot_id)
        flash(result["message"], result["category"])
        return redirect(url_for(result["redirect"]))
    
    today_str = datetime.now(IST).strftime('%Y-%m-%d')

    return render_template("donor-book.html", current_date = today_str)