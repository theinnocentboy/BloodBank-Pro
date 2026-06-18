"""OTP Management Routes"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from datetime import datetime

from bloodbank.decorators import login_required
from bloodbank.extensions import db
from bloodbank.models import User
from bloodbank.otp_utils import (
    generate_otp_secret,
    generate_qr_code,
    verify_otp_token,
    generate_backup_codes
)

otp_bp = Blueprint("otp", __name__, url_prefix="/otp")


@otp_bp.route("/setup", methods=["GET", "POST"])
@login_required
def setup_otp():
    """Setup OTP authentication for user."""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("user.dashboard"))
    
    if user.otp_enabled:
        flash("OTP is already enabled for your account.", "info")
        return redirect(url_for("user.profile"))
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "generate_secret":
            # Generate new secret and QR code
            secret = generate_otp_secret()
            qr_code = generate_qr_code(user.username, secret)
            
            session["pending_otp_secret"] = secret
            session["pending_otp_qr"] = qr_code
            
            return render_template(
                "otp-setup.html",
                secret=secret,
                qr_code=qr_code,
                step="verify"
            )
        
        elif action == "verify_otp":
            # Verify OTP code entered by user
            pending_secret = session.get("pending_otp_secret")
            otp_code = request.form.get("otp_code", "").strip()
            
            if not pending_secret or not otp_code:
                flash("Invalid request. Please try again.", "danger")
                return redirect(url_for("otp.setup_otp"))
            
            if not verify_otp_token(pending_secret, otp_code):
                flash("Invalid OTP code. Please try again.", "danger")
                secret = pending_secret
                qr_code = session.get("pending_otp_qr")
                return render_template(
                    "otp-setup.html",
                    secret=secret,
                    qr_code=qr_code,
                    step="verify"
                )
            
            # OTP verified, enable it
            user.otp_secret = pending_secret
            user.otp_enabled = True
            user.otp_verified_at = datetime.utcnow()
            user.otp_backup_codes = generate_backup_codes()
            
            db.session.commit()
            
            # Clean up session
            session.pop("pending_otp_secret", None)
            session.pop("pending_otp_qr", None)
            
            flash("OTP has been successfully enabled!", "success")
            return render_template(
                "otp-backup-codes.html",
                backup_codes=user.otp_backup_codes.split(",")
            )
    
    return render_template("otp-setup.html", step="generate")


@otp_bp.route("/disable", methods=["POST"])
@login_required
def disable_otp():
    """Disable OTP authentication for user."""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("user.dashboard"))
    
    password = request.form.get("password", "")
    
    # Verify password
    if not user.check_password(password):
        flash("Incorrect password.", "danger")
        return redirect(url_for("user.profile"))
    
    # Disable OTP
    user.otp_enabled = False
    user.otp_secret = None
    user.otp_backup_codes = None
    user.manual_otp_code = None
    user.manual_otp_expires_at = None
    
    db.session.commit()
    
    flash("OTP has been disabled.", "success")
    return redirect(url_for("user.profile"))


@otp_bp.route("/regenerate-backup-codes", methods=["POST"])
@login_required
def regenerate_backup_codes():
    """Regenerate backup codes."""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("user.dashboard"))
    
    if not user.otp_enabled:
        flash("OTP is not enabled.", "danger")
        return redirect(url_for("user.profile"))
    
    password = request.form.get("password", "")
    
    # Verify password
    if not user.check_password(password):
        flash("Incorrect password.", "danger")
        return redirect(url_for("user.profile"))
    
    # Generate new backup codes
    user.otp_backup_codes = generate_backup_codes()
    db.session.commit()
    
    flash("Backup codes have been regenerated.", "success")
    return render_template(
        "otp-backup-codes.html",
        backup_codes=user.otp_backup_codes.split(",")
    )


@otp_bp.route("/send-manual-code", methods=["POST"])
def send_manual_otp_code():
    """Reset/manual OTP fallback endpoint.

    SMTP-based OTP delivery is disabled in the current configuration.
    """
    pending_user_id = session.get("pending_user_id")
    
    if not pending_user_id:
        flash("Invalid request.", "danger")
        return redirect(url_for("auth.login"))
    
    user = User.query.get(pending_user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.login"))
    
    # Email delivery is intentionally disabled after SMTP reset.
    flash("Email-based OTP delivery is disabled. Use your authenticator app or a backup code.", "warning")
    
    return redirect(url_for("auth.verify_otp"))
