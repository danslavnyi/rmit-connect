#!/usr/bin/env python3
"""
RMIT Connect - Campus Social Network Application

Main entry point for the Flask application.
Handles application startup, configuration, and server initialization.

Author: RMIT Connect Team
Version: 1.0.0
"""

import os
import sys
import logging
from typing import NoReturn

# Application imports
from app import app, db
import routes  # noqa: F401 - Import needed for route registration

# Make app available at module level for gunicorn
application = app


def configure_logging() -> None:
    """Configure application logging for different environments."""
    if os.environ.get('FLASK_ENV') == 'production':
        # Production logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    else:
        # Development logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )


def initialize_database() -> None:
    """Initialize database tables if they don't exist."""
    try:
        with app.app_context():
            db.create_all()
            logging.info("Database tables initialized successfully")
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
        sys.exit(1)


def get_server_config() -> tuple[str, int, bool]:
    """Get server configuration from environment variables."""
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') != 'production'

    return host, port, debug


def main() -> NoReturn:
    """Main application entry point."""
    # Configure logging first
    configure_logging()

    # Log startup information
    logging.info("Starting RMIT Connect application...")
    logging.info(f"Environment: {os.environ.get('FLASK_ENV', 'development')}")

    # Initialize database
    initialize_database()

    # Get server configuration
    host, port, debug = get_server_config()

    # Log server information
    logging.info(f"Server starting on {host}:{port}")
    logging.info(f"Debug mode: {debug}")

    try:
        # Start the Flask application
        app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        logging.info("Application stopped by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Application failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
