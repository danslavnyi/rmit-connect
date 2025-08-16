"""
Flask application factory and configuration for RMIT Connect.

This module initializes the Flask application with all necessary extensions,
security configurations, and middleware for the RMIT Connect platform.

Author: RMIT Connect Team
Version: 1.0.0
"""

import os
import logging
from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_compress import Compress
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Application imports
from security import secure_headers, generate_csrf_token
from config import get_config

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Configure logging based on environment
environment = os.environ.get('FLASK_ENV', 'development')
if environment == 'production':
    logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.DEBUG)


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)

# Load configuration based on environment
config = get_config()
app.config.from_object(config)

# Initialize compression for better performance
compress = Compress(app)

# Apply proxy fix for production deployment (important for Heroku)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Initialize the app with the extension
db.init_app(app)

# Initialize Flask-Mail (configuration comes from config class)
mail = Mail(app)

# Initialize Flask-Login with security settings
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'
login_manager.session_protection = "strong"  # Enhanced session protection

# Apply security headers to all responses
app.after_request(secure_headers())

# Add performance optimizations


@app.after_request
def add_performance_headers(response):
    # Cache static files for 1 year
    if 'static' in request.path:
        response.cache_control.max_age = 31536000  # 1 year
        response.cache_control.public = True

    # Add compression hints
    if response.content_type and any(mime in response.content_type for mime in
                                     ['text/', 'application/json', 'application/javascript']):
        response.headers['Vary'] = 'Accept-Encoding'

    return response

# Make CSRF token available in templates


@app.before_request
def inject_csrf_token():
    g.csrf_token = generate_csrf_token()


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))


with app.app_context():
    # Import models to ensure tables are created
    import models  # noqa: F401
    import routes  # noqa: F401

    # Only create tables if not in production or if tables don't exist
    try:
        db.create_all()
        logging.info("Database tables created successfully")
    except Exception as e:
        logging.warning(
            f"Database table creation issue (may already exist): {e}")

    # Ensure upload folder exists with proper permissions
    upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, mode=0o755, exist_ok=True)
        logging.info(f"Created upload folder: {upload_folder}")

    logging.info("Database tables and upload folder initialized")
