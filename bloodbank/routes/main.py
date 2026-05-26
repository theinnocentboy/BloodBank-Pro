from flask import Blueprint, render_template, current_app, send_from_directory
import os

from bloodbank.models import BloodInventory, BloodRequest, Donor

main_bp = Blueprint("main", __name__)


@main_bp.route("/favicon.ico")
def favicon():
    return send_from_directory(current_app.static_folder, "favicon.ico", mimetype="image/x-icon")


@main_bp.route("/")
def home():
    stats = {
        "donors": Donor.query.filter_by(availability=True).count(),
        "units": sum(item.units for item in BloodInventory.query.all()),
        "fulfilled": BloodRequest.query.filter_by(status="approved").count(),
    }
    return render_template("index.html", stats=stats)


@main_bp.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")


@main_bp.route("/debug-config")
def debug_config():
    return {
        "AUTH0_CLIENT_ID": current_app.config.get("AUTH0_CLIENT_ID"),
        "AUTH0_DOMAIN": current_app.config.get("AUTH0_DOMAIN"),
        "AUTH0_GOOGLE_CONNECTION": current_app.config.get("AUTH0_GOOGLE_CONNECTION"),
        "AUTH0_FACEBOOK_CONNECTION": current_app.config.get("AUTH0_FACEBOOK_CONNECTION"),
    }
