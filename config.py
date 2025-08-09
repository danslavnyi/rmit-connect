"""
Configuration management for RMIT Connect application.

This module contains all configuration classes for different environments
including development, production, and testing configurations.

Author: RMIT Connect Team
Version: 1.0.0
"""

import os
import secrets
from datetime import timedelta
from typing import Dict, Any


class Config:
    """Base configuration class with security best practices."""

    # Security - Secret Key
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)

    # Security - Session Configuration
    SESSION_COOKIE_SECURE = True  # Only send cookies over HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)  # Session expiry

    # Security - Content Security Policy
    CSP_POLICY = {
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        'style-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        'img-src': "'self' data: https:",
        'font-src': "'self' https://cdn.jsdelivr.net",
        'connect-src': "'self'",
        'frame-ancestors': "'none'",
    }

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL') or 'sqlite:///campusconnect.db'
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "echo": False  # Disable SQL logging for performance
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Performance optimizations
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year cache for static files
    COMPRESS_MIMETYPES = [
        'text/html', 'text/css', 'text/xml', 'application/json',
        'application/javascript', 'text/javascript', 'image/svg+xml'
    ]

    # Security Headers
    FORCE_HTTPS = True
    HSTS_MAX_AGE = 31536000  # 1 year

    # Rate Limiting
    RATE_LIMIT_STORAGE_URL = os.environ.get('REDIS_URL') or 'memory://'


class DevelopmentConfig(Config):
    """Development configuration - less strict security for testing"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development
    FORCE_HTTPS = False

    # Email configuration for development
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')

    # Development file uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4MB limit

    # Allowed file extensions for uploads
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


class ProductionConfig(Config):
    """Production configuration - maximum security"""
    DEBUG = False
    TESTING = False

    # Enhanced security for production
    SESSION_COOKIE_SECURE = True
    FORCE_HTTPS = True
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=30)  # 30 minutes for production

    # Database security - PostgreSQL for production
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///campusconnect.db'

    # Enhanced database configuration for production
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "pool_size": 20,  # Increased for production
        "max_overflow": 40,  # Increased for production
        "pool_timeout": 30,
        "echo": False
    }

    # Email configuration for production
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')

    # Production file uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4MB limit

    # Security enhancements
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour

    # Logging for production
    LOG_LEVEL = 'INFO'

    # Allowed file extensions for uploads
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# Configuration selection
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on environment"""
    environment = os.environ.get('FLASK_ENV', 'development')
    return config.get(environment, config['default'])
