"""Donor-facing business logic for BloodBank."""

from __future__ import annotations

from datetime import datetime

import pytz
from flask import current_app
from sqlalchemy.orm import joinedload

from bloodbank.constants import BLOOD_GROUPS
from bloodbank.decorators import verified_required
from bloodbank.extensions import db
from bloodbank.models import DonationAppointment, DonationSlot, Donor, User
from bloodbank.utils import calculate_age

IST = pytz.timezone("Asia/Kolkata")


def _response(success, message, category="info", redirect=None, render=None, context=None):
    return {
        "success": success,
        "message": message,
        "category": category,
        "redirect": redirect,
        "render": render,
        "context": context or {},
    }


def search_donors(blood_group=None, city=None):
    query = Donor.query.options(joinedload(Donor.user)).filter_by(availability=True)
    if blood_group:
        query = query.filter_by(blood_group=blood_group)
    if city:
        query = query.filter(Donor.city.ilike(f"%{city}%"))
    donors = query.all()
    return donors


def list_available_donors():
    return Donor.query.options(joinedload(Donor.user)).filter_by(availability=True).all()


def register_donor(user_id, blood_group, city):
    user = db.session.get(User, user_id)
    if not user:
        return _response(False, "Session expired. Please log in again.", "warning", redirect="auth.login")

    existing = Donor.query.filter_by(user_id=user.id).first()
    if existing:
        return _response(False, "You are already registered as a donor.", "info", redirect="user.dashboard")

    if not user.dob:
        return _response(False, "Medical Policy: You must provide your Date of Birth in the Personal tab before registering as a donor.", "warning", redirect="user.profile")

    age = calculate_age(user.dob)
    if age < 18:
        return _response(False, f"Clinical Restriction: You are {age} years old. Medical regulations require blood donors to be at least 18.", "danger", redirect="user.profile")

    if age > 65:
        return _response(False, "Clinical Restriction: For cardiovascular safety, blood donation is restricted to individuals 65 years and younger.", "danger", redirect="user.profile")

    if blood_group not in BLOOD_GROUPS or not city:
        return _response(False, "Blood group and city are required.", "danger", redirect="donor.register_donor")

    donor = Donor(user_id=user.id, blood_group=blood_group, city=city)
    db.session.add(donor)
    db.session.commit()
    return _response(True, "You are now registered as a donor.", "success", redirect="user.dashboard")


def get_available_slots(date_str):
    try:
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date"}, 400

    available_slots = DonationSlot.query.filter_by(date=query_date, is_locked=False).all()

    valid_slots = []
    for slot in available_slots:
        current_bookings = slot.appointments.count()
        if current_bookings < slot.max_capacity:
            valid_slots.append(
                {
                    "slot_id": slot.id,
                    "time": slot.time_string,
                    "remaining": slot.max_capacity - current_bookings,
                }
            )

    return {"slots": valid_slots}, 200


def book_appointment(user_id, slot_id):
    donor = Donor.query.filter_by(user_id=user_id).first()
    if not donor:
        return _response(False, "You must register as a donor first.", "warning", redirect="donor.register_donor")

    if not slot_id:
        return _response(False, "Please select a valid time slot.", "danger", redirect="donor.book_appointment")

    slot = db.session.get(DonationSlot, slot_id)
    if not slot or slot.is_locked:
        return _response(False, "This slot is no longer available. Please choose another.", "danger", redirect="donor.book_appointment")

    if slot.appointments.count() >= slot.max_capacity:
        return _response(False, "This slot has reached maximum capacity.", "warning", redirect="donor.book_appointment")

    existing = DonationAppointment.query.filter_by(donor_id=donor.id, status="scheduled").first()
    if existing:
        return _response(False, "You already have an appointment scheduled. Please wait for this to be processed.", "info", redirect="user.dashboard")

    new_appointment = DonationAppointment(
        donor_id=donor.id,
        slot_id=slot.id,
        appointment_date=slot.date,
        time_slot=slot.time_string,
        status="scheduled",
    )
    db.session.add(new_appointment)
    db.session.commit()
    return _response(True, "Appointment request submitted successfully!", "success", redirect="user.dashboard")


def update_donor_profile(user_id, form):
    donor = Donor.query.filter_by(user_id=user_id).first()
    if not donor:
        return _response(False, "You are not registered as a donor.", "warning", redirect="user.profile")

    blood_group = form.get("blood_group", "").strip()
    city = form.get("city", "").strip()
    availability = form.get("availability") == "1"

    if blood_group not in BLOOD_GROUPS or not city:
        return _response(False, "Blood group and city are required.", "danger", redirect="user.profile")

    donor.blood_group = blood_group
    donor.city = city
    donor.availability = availability
    db.session.commit()
    return _response(True, "Donor profile updated successfully.", "success", redirect="user.profile")
