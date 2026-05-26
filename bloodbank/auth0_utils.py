"""Auth0 Integration Utilities"""

import json
import os
import requests
from authlib.integrations.flask_client import OAuth
from flask import current_app
from functools import wraps
from flask import session, redirect, url_for

oauth = OAuth()


def get_connection_name(provider: str) -> str:
    """Map provider name to Auth0 connection name.

    Args:
        provider: Provider name (google, facebook, etc.)

    Returns:
        Auth0 connection name for the provider
    """
    connections = {
        'google': os.environ.get('AUTH0_GOOGLE_CONNECTION', 'google-oauth2'),
        'facebook': os.environ.get('AUTH0_FACEBOOK_CONNECTION', 'facebook'),
    }
    return connections.get(provider, provider)


def init_auth0(app):
    """Initialize Auth0 OAuth client."""
    oauth.init_app(app)

    auth0_domain = app.config.get('AUTH0_DOMAIN')
    auth0_client_id = app.config.get('AUTH0_CLIENT_ID')
    auth0_client_secret = app.config.get('AUTH0_CLIENT_SECRET')

    # Register OAuth client
    if auth0_domain:
        oauth.register(
            'auth0',
            client_id=auth0_client_id,
            client_secret=auth0_client_secret,
            client_kwargs={
                'scope': 'openid profile email',
            },
            server_metadata_url=f"https://{auth0_domain}/.well-known/openid-configuration"
        )
    else:
        # Fallback registration with manual URLs if domain not available
        oauth.register(
            'auth0',
            client_id=auth0_client_id,
            client_secret=auth0_client_secret,
            access_token_url='https://dev-4xtoqze1fu6h6j5k.us.auth0.com/oauth/token',
            authorize_url='https://dev-4xtoqze1fu6h6j5k.us.auth0.com/authorize',
            client_kwargs={
                'scope': 'openid profile email',
            }
        )

    return oauth


def get_auth0_user_info(access_token):
    """Get user info from Auth0 using access token.
    
    Args:
        access_token: Auth0 access token
    
    Returns:
        Dictionary with user info or None if failed
    """
    try:
        url = f"https://{current_app.config.get('AUTH0_DOMAIN')}/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        current_app.logger.error(f"Error getting Auth0 user info: {e}")
        return None


def requires_auth0_token(f):
    """Decorator to require Auth0 authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'auth0_token' not in session:
            return redirect(url_for('auth.login_with_auth0'))
        return f(*args, **kwargs)
    return decorated_function


class Auth0Error(Exception):
    """Auth0 specific error."""
    pass
