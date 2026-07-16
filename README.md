# BloodBank Pro

BloodBank Pro is a Flask-based blood management system for donor registration, blood requests, inventory tracking, and OTP-protected user access.

## Features

- Public user registration and login
- Dedicated admin and superadmin areas
- OTP-based 2FA with authenticator app support and backup codes
- Blood donor browsing, booking, and request workflows
- AI/ML helpers for chatbot, recommendation, and demand prediction

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Then open http://127.0.0.1:5000 in your browser.

## Configuration

Set environment variables as needed before starting the app:

- `SECRET_KEY`: session signing key
- `DATABASE_URL`: optional database URI override, defaults to SQLite under `instance/`
- `FLASK_DEBUG`: set to `0` to run without debug mode
- `SUPERADMIN_USER`, `SUPERADMIN_PASS`, `SUPERADMIN_EMAIL`: optional bootstrap credentials used by `run.py`
- `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_CALLBACK_URL`: required only when Auth0 login is enabled

## Project Layout

- `run.py`: application entrypoint
- `bloodbank/`: Flask app package, models, utilities, routes, and AI/ML helpers
- `templates/`: Jinja templates for public, admin, and OTP flows
- `static/`: CSS and JavaScript assets
- `instance/`: local runtime files such as uploads, requisitions, and the SQLite database

## Notes

- `run.py` seeds or restores the superadmin account when the related environment variables are present.
- OTP setup and verification are handled through the profile and login flows in the app.
- The repository includes generated or local-only runtime files under `instance/`, which should remain untracked.
