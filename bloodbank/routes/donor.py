from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from bloodbank.constants import BLOOD_GROUPS
from bloodbank.decorators import login_required
from bloodbank.extensions import db
from bloodbank.models import Donor, User

donor_bp = Blueprint("donor", __name__)


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

        if blood_group not in BLOOD_GROUPS or not city:
            flash("Blood group and city are required.", "danger")
            return redirect(url_for("donor.register_donor"))

        donor = Donor(user_id=user.id, blood_group=blood_group, city=city)
        db.session.add(donor)
        db.session.commit()
        flash("You are now registered as a donor.", "success")
        return redirect(url_for("user.dashboard"))

    return render_template("donor-register.html", blood_groups=BLOOD_GROUPS)
