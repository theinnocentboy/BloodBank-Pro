import os
from pathlib import Path

from flask import Flask
from dotenv import load_dotenv

from bloodbank.config import Config
from bloodbank.extensions import db
from bloodbank.seed import seed_database

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_class=Config):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    
    # Initialize Auth0
    from bloodbank.auth0_utils import init_auth0
    init_auth0(app)

    from bloodbank.routes import register_blueprints

    register_blueprints(app)

    # Make config available to all templates
    @app.context_processor
    def inject_config():
        return dict(config=app.config)

    with app.app_context():
        db.create_all()
        seed_database()

    return app
