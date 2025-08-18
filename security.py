"""
Security utilities for the RMIT Connect app
Implements security best practices for data protection
"""

import secrets
import re
from functools import wraps
from flask import request, abort, g
import time


class SecurityUtils:
    """Security utilities class"""

    @staticmethod
    def generate_secure_token(length=32):
        """Generate a cryptographically secure random token"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def sanitize_user_input(text):
        """Basic input sanitization"""
        if not text:
            return ""
        # Remove potential script tags and dangerous characters
        text = re.sub(r'<script.*?</script>', '', text,
                      flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
        text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def validate_email_security(email):
        """Enhanced email validation with security checks"""
        if not email or len(email) > 320:  # RFC 5321 limit
            return False

        # Basic format validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False

        # Check for suspicious patterns
        suspicious_patterns = [
            r'\.{2,}',  # Multiple consecutive dots
            r'^\.|\.$',  # Starting or ending with dot
            r'@.*@',  # Multiple @ symbols
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, email):
                return False

        return True


class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(self):
        self.requests = {}
        self.blocked_ips = {}

    def is_allowed(self, identifier, max_requests=100, window=3600):
        """Check if request is allowed based on rate limits"""
        current_time = time.time()

        # Check if IP is temporarily blocked
        if identifier in self.blocked_ips:
            if current_time < self.blocked_ips[identifier]:
                return False
            else:
                del self.blocked_ips[identifier]

        # Clean old requests
        if identifier in self.requests:
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if current_time - req_time < window
            ]
        else:
            self.requests[identifier] = []

        # Check rate limit
        if len(self.requests[identifier]) >= max_requests:
            # Block IP for 1 hour
            self.blocked_ips[identifier] = current_time + 3600
            return False

        # Add current request
        self.requests[identifier].append(current_time)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter()


def require_rate_limit(max_requests=100, window=3600):
    """Decorator for rate limiting endpoints"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            identifier = request.environ.get(
                'HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))

            if not rate_limiter.is_allowed(identifier, max_requests, window):
                abort(429)  # Too Many Requests

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def generate_csrf_token():
    """Generate CSRF token for forms"""
    if 'csrf_token' not in g:
        g.csrf_token = SecurityUtils.generate_secure_token(16)
    return g.csrf_token


def secure_headers():
    """Add security headers to responses"""
    def after_request(response):
        # Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # HSTS header for HTTPS
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # Content Security Policy
        csp = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' https://cdn.jsdelivr.net"
        response.headers['Content-Security-Policy'] = csp

        return response

    return after_request
