from bloodbank.routes.admin import admin_bp
from bloodbank.routes.auth import auth_bp
from bloodbank.routes.donor import donor_bp
from bloodbank.routes.main import main_bp
from bloodbank.routes.user import user_bp
from bloodbank.routes.otp import otp_bp
from bloodbank.routes.ai_routes import ai_bp
from bloodbank.routes.api import chatbot_bp  # <-- Import the new chatbot blueprint
from bloodbank.routes.superadmin import superadmin_bp



def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(donor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(otp_bp)
    app.register_blueprint(ai_bp)  # Register existing AI/ML routes
    app.register_blueprint(chatbot_bp)  # <-- Register the chatbot routes
    app.register_blueprint(superadmin_bp)