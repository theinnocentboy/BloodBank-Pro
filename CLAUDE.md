# Blood Bank Management System - Project Documentation

## Project Overview

A Flask-based Blood Bank Management System with AI/ML features for intelligent donor matching, demand prediction, and emergency prioritization.

### Core Features
- User registration & authentication with OTP support
- Donor registration and management
- Blood request tracking with urgency levels
- Admin dashboard with analytics
- Inventory management (stock tracking & deductions)
- AI-powered donor recommendations
- Location-based donor matching
- Emergency request prioritization
- Optional Auth0 OAuth integration

## Project Structure

```
blood/
├── bloodbank/                    # Main application package
│   ├── __init__.py              # App factory (create_app)
│   ├── config.py                # Configuration settings
│   ├── extensions.py            # SQLAlchemy instance
│   ├── models.py                # Database models
│   ├── seed.py                  # Database seeding (demo data)
│   ├── constants.py             # Application constants
│   ├── decorators.py            # Custom decorators
│   ├── auth0_utils.py           # Optional Auth0 integration
│   ├── email_utils.py           # Email sending utilities
│   ├── otp_utils.py             # OTP generation/verification
│   ├── routes/                  # Flask blueprints
│   │   ├── __init__.py          # Blueprint registration
│   │   ├── main.py              # Public routes (home, about)
│   │   ├── auth.py              # Login/register/logout
│   │   ├── user.py              # User profile management
│   │   ├── donor.py             # Donor operations
│   │   ├── admin.py             # Admin dashboard
│   │   ├── otp.py               # Two-factor authentication
│   │   └── ai_routes.py         # AI/ML features endpoints
│   └── ai_ml/                   # AI/ML modules
│       ├── donor_recommendation.py    # Smart donor matching
│       ├── location_matching.py       # Geographic matching
│       ├── demand_prediction.py       # ML demand forecasting
│       ├── emergency_priority.py      # Urgency scoring
│       ├── chatbot_assistant.py       # AI chatbot
│       └── utils.py                   # Helper functions
├── templates/                   # Jinja2 HTML templates
├── static/                      # CSS, JS, images
├── instance/                    # Instance folder (databases, logs)
├── run.py                       # Application entry point
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── README.md                    # User-facing documentation
└── CLAUDE.md                    # This file
```

## Technology Stack

- **Backend:** Flask 3.0.3, SQLAlchemy 3.1.1
- **Frontend:** Jinja2 templates, Bootstrap 5, Chart.js
- **Database:** SQLite (production can use PostgreSQL)
- **Authentication:** Local accounts + optional Auth0 OAuth
- **Security:** Password hashing (Werkzeug), OTP (pyotp)
- **AI/ML:** scikit-learn (demand prediction)
- **Email:** SMTP integration (Gmail, Office365, custom)

## Setup & Running

### Installation
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### Environment Setup
Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
# Edit .env with your configuration
```

**Required variables:**
- `SECRET_KEY` - Session encryption key

**Optional variables:**
- Auth0 integration: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`
- Email: `SMTP_SERVER`, `SMTP_USERNAME`, `SMTP_PASSWORD`

### Demo Credentials
| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin |
| User | user1 | password |

## Code Guidelines

### Architecture Decisions
- **Blueprints for modular routes** - Each feature (auth, donor, admin) is isolated
- **Factory pattern for app creation** - Enables testing and multiple configurations
- **SQLAlchemy ORM** - No raw SQL; consistent database abstraction
- **Optional Auth0 integration** - Gracefully degrades if not configured

### Dependencies Removed (Not Essential)
- `auth0-server-python` - Replaced by authlib
- `geopy` - Location matching uses Haversine formula
- `matplotlib` - No server-side plotting needed
- `joblib` - Not directly used
- `flask[async]` - Not utilized

### File Conventions
- Database models: `models.py` only
- Route blueprints: Individual files in `routes/`
- AI/ML logic: Separate `ai_ml/` package
- Utilities: `*_utils.py` files (auth0_utils, email_utils, otp_utils)

### Common Patterns
- `decorators.py` - Custom decorators (e.g., login_required)
- `constants.py` - Shared constants (blood types, request statuses)
- `extensions.py` - Shared extension instances (db, cache)
- `seed.py` - Database initialization on first run

## Development Notes

### Database
- SQLite for development (`instance/blood.db`)
- Auto-created on first run via `seed_database()`
- Models in `models.py`: User, Donor, BloodRequest, Inventory, etc.

### Authentication
- **Local Auth:** Email/username + password (hashed with Werkzeug)
- **OTP:** Optional 2FA using time-based OTP (TOTP) with pyotp
- **Auth0:** Gracefully optional—app works without credentials

### Logs & Debugging
- Set `FLASK_DEBUG=1` in `.env` for development
- Set `FLASK_DEBUG=0` for production
- Logs appear in console; can be extended to files

### Testing
Current setup: Manual testing via web UI. Consider adding:
- Unit tests for models and utilities
- Integration tests for routes
- Test database fixtures

## Common Tasks

### Adding a New Route
1. Create file in `bloodbank/routes/` (e.g., `request.py`)
2. Define a blueprint and routes
3. Import and register in `bloodbank/routes/__init__.py`

### Adding a Database Model
1. Define class in `bloodbank/models.py` inheriting from `db.Model`
2. Add relationships as needed
3. Models auto-create on app startup

### Adding AI/ML Feature
1. Create module in `bloodbank/ai_ml/` (e.g., `fraud_detection.py`)
2. Implement feature class or functions
3. Call from routes via `ai_routes.py`

## Cleanup & Maintenance

### Removed (Not Essential)
- ✅ `auth0-flask-app/` directory - Legacy venv folder
- ✅ `__pycache__/` directories - Python cache
- ✅ Unused dependencies: geopy, matplotlib, joblib, auth0-server-python

### Updated
- ✅ `.gitignore` - Comprehensive patterns
- ✅ `requirements.txt` - Only essential dependencies
- ✅ `auth0_utils.py` - Graceful Auth0 initialization
- ✅ `.env.example` - Template for environment variables

### Never Commit
- `.env` - Contains sensitive credentials
- `instance/` - Contains SQLite database files
- `.venv/` - Virtual environment
- `__pycache__/` - Python cache
- `.pyc` files - Compiled Python

## Deployment Checklist

- [ ] Set unique `SECRET_KEY` in production `.env`
- [ ] Set `FLASK_DEBUG=0`
- [ ] Configure database URL (PostgreSQL recommended for production)
- [ ] Setup SMTP credentials for email notifications
- [ ] Configure CORS if frontend is separate domain
- [ ] Enable HTTPS in production
- [ ] Setup logging to file or service
- [ ] Consider Auth0 integration for SSO
