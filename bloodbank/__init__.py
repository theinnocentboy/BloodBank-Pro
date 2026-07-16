import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, session, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix

# Base directory setup
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
env_file = BASE_DIR / ".env"
load_dotenv(dotenv_path=str(env_file))

# Import your configurations and extensions
from bloodbank.config import Config
from bloodbank.extensions import db
from bloodbank.models import User
from bloodbank.seed import seed_database
from bloodbank.auth0_utils import init_auth0
from bloodbank.routes import register_blueprints

def create_app(config_class=Config):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_object(config_class)

    # --- RENDER & AWS DEPLOYMENT PROXY FIX ---
    # This forces Flask to respect HTTPS headers sent by Render's reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    
    # Initialize Auth0
    init_auth0(app)

    # Register all blueprints
    register_blueprints(app)

    # --- GLOBAL SECURITY GATEKEEPER ---
    @app.before_request
    def check_user_status():
        """
        Globally checks if the logged-in user has been banned.
        Redirects based on user role to ensure they end up at the correct login page.
        """
        if 'user_id' in session:
            # Check the database for the user's current status
            user = User.query.get(session.get('user_id'))
            
            # If user exists but is_active is False, revoke access immediately
            if user and not getattr(user, 'is_active', True):
                user_role = user.role # Get role before clearing session
                session.clear() 
                flash('Your account has been suspended by an administrator.', 'danger')
                
                # Logic: Redirect Admins/Superadmins to Admin Login, everyone else to User Login
                if user_role in ['admin', 'superadmin']:
                    return redirect(url_for('admin.admin_login'))
                else:
                    return redirect(url_for('auth.login'))

    # Make config available to all templates
    @app.context_processor
    def inject_config():
        return dict(config=app.config)

    # Database initialization
    with app.app_context():
        db.create_all()
        seed_database()

    return app