from functools import wraps

from flask import flash, redirect, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


from functools import wraps
from flask import session, flash, redirect, url_for

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # Using your existing check for 'role' == 'admin'
        if 'user_id' not in session or session.get('role') not in ['admin', 'superadmin']:
            flash('You do not have permission to access the admin command center.', 'danger')
            # Redirecting to the dedicated admin login
            return redirect(url_for("admin.admin_login"))
        return view(*args, **kwargs)

    return wrapped

def superadmin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # Strict check: Must be logged in AND specifically hold the 'superadmin' role
        if "user_id" not in session or session.get("role") != "superadmin":
            flash("CRITICAL: Super Administrator clearance required.", "danger")
            # Kick unauthorized users to the admin login page
            return redirect(url_for("admin.admin_login"))
        return view(*args, **kwargs)

    return wrapped

def verified_required(view):
    """Restricts route access to users with verified phone numbers."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        from bloodbank.models import User 
        from bloodbank.extensions import db
        
        user = db.session.get(User, session.get("user_id"))
        
        if not user or not user.email_verified:
            flash("Action Restricted: You must verify your mobile number to use this clinical feature.", "danger")
            return redirect(url_for("user.dashboard"))
            
        return view(*args, **kwargs)

    return wrapped