import os
from werkzeug.security import generate_password_hash

from bloodbank import create_app
from bloodbank.extensions import db
from bloodbank.models import User

app = create_app()

def seed_superadmin():
    """Securely injects the Master Super Admin if environment variables are present."""
    sa_username = os.environ.get("SUPERADMIN_USER")
    sa_password = os.environ.get("SUPERADMIN_PASS")
    sa_email = os.environ.get("SUPERADMIN_EMAIL", "boss@bloodbank.local")

    if sa_username and sa_password:
        existing_user = User.query.filter_by(username=sa_username).first()
        
        if not existing_user:
            print(f"[*] Deploying Master Super Admin account: @{sa_username}...")
            super_admin = User(
                username=sa_username,
                email=sa_email,
                full_name="Global System Director",
                password_hash=generate_password_hash(sa_password),
                role="superadmin", # This alone makes the @property is_admin return True
                email_verified=True
            )
            db.session.add(super_admin)
            db.session.commit()
            print("[+] Super Admin deployed successfully into the database.")
        else:
            if existing_user.role != "superadmin":
                existing_user.role = "superadmin"
                db.session.commit()
                print(f"[*] Restored Super Admin privileges to @{sa_username}.")

if __name__ == "__main__":
    with app.app_context():
        seed_superadmin()
        
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5000, use_reloader=False)