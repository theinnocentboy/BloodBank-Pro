# BloodBank — Blood Management System

A Flask web app for donor registration, blood requests, inventory tracking, and admin management.

## Features

- User registration and login with hashed passwords
- Donor search and registration
- Blood requests with urgency levels
- Admin dashboard with charts, user/donor/request management
- Inventory tracking (deducts stock when requests are approved)

## Quick start

```bash
cd blood
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000

### Demo accounts

| Role  | Username | Password  |
|-------|----------|-----------|
| Admin | admin    | admin     |
| User  | user1    | password  |

## Project structure

```
blood/
├── bloodbank/          # Application package
│   ├── models.py       # Database models
│   ├── routes/         # Blueprints (auth, user, donor, admin)
│   ├── seed.py         # Default admin, demo user, inventory
│   └── config.py
├── templates/          # Jinja2 HTML templates
├── static/             # CSS and JavaScript
├── instance/           # SQLite database (auto-created)
└── run.py              # Entry point
```

## Configuration

Set environment variables (optional):

- `SECRET_KEY` — session signing key
- `DATABASE_URL` — database URI (default: SQLite in `instance/blood.db`)
- `FLASK_DEBUG` — set to `0` in production

## Tech stack

Flask 3, SQLAlchemy, Bootstrap 5, Chart.js
