"""WSGI entrypoint for Gunicorn."""

from bloodbank import create_app

app = create_app()
