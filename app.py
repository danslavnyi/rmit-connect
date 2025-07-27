from security import secure_headers, generate_csrf_token
from config import get_config
import os
import logging
from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

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
    db.create_all()
    logging.info("Database tables created")
