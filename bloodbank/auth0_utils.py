"""Auth0 Integration Utilities"""

import json
import os
from authlib.integrations.flask_client import OAuth
from flask import current_app, session
from urllib.parse import urlencode

oauth = OAuth()


def get_connection_name(provider: str) -> str:
    """Map provider name to Auth0 connection name."""
    connections = {
        'google': os.environ.get('AUTH0_GOOGLE_CONNECTION', 'google-oauth2'),
        'facebook': os.environ.get('AUTH0_FACEBOOK_CONNECTION', 'facebook'),
    }
    return connections.get(provider, provider)


def init_auth0(app):
    """Initialize Auth0 OAuth client."""
    auth0_domain = app.config.get('AUTH0_DOMAIN')
    auth0_client_id = app.config.get('AUTH0_CLIENT_ID')
    
    if not auth0_domain or not auth0_client_id:
        app.logger.warning("Auth0 credentials not configured. Auth0 login will be disabled.")
        return oauth
    
    oauth.init_app(app)
    
    # Register Auth0 client
    oauth.register(
        'auth0',
        client_id=auth0_client_id,
        client_secret=app.config.get('AUTH0_CLIENT_SECRET'),
        api_base_url=f"https://{auth0_domain}",
        access_token_url=f"https://{auth0_domain}/oauth/token",
        authorize_url=f"https://{auth0_domain}/authorize",
        client_kwargs={
            'scope': 'openid profile email',
        },
        server_metadata_url=f"https://{auth0_domain}/.well-known/openid-configuration",
    )
    
    app.logger.info("Auth0 integration initialized successfully.")
    return oauth


def get_auth0_user_info(userinfo):
    """Extract user information from Auth0 userinfo."""
    if not userinfo:
        return None
    
    return {
        'email': userinfo.get('email'),
        'full_name': userinfo.get('name', userinfo.get('email', '')),
        'picture': userinfo.get('picture'),
        'auth0_id': userinfo.get('sub'),  # Unique Auth0 identifier
    }


def is_auth0_enabled() -> bool:
    """Check if Auth0 is properly configured."""
    return bool(
        current_app.config.get('AUTH0_DOMAIN') and 
        current_app.config.get('AUTH0_CLIENT_ID')
    )


class Auth0Error(Exception):
    """Auth0 specific error."""
    pass

