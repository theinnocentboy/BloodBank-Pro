from bloodbank.routes.admin import admin_bp
from bloodbank.routes.auth import auth_bp
from bloodbank.routes.donor import donor_bp
from bloodbank.routes.main import main_bp
from bloodbank.routes.user import user_bp
from bloodbank.routes.otp import otp_bp
from bloodbank.routes.ai_routes import ai_bp


def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(donor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(otp_bp)
    app.register_blueprint(ai_bp)  # Register AI/ML routes
