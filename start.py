#!/usr/bin/env python3
"""
Production startup script for RMIT Connect on Render.

This script handles graceful startup with proper error handling
and timeout management for cloud deployment.
"""

import os
import sys
import time
import logging
from typing import NoReturn

# Configure basic logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def wait_for_startup():
    """Add a small delay to ensure services are ready."""
    startup_delay = int(os.environ.get('STARTUP_DELAY', '2'))
    if startup_delay > 0:
        logger.info(
            f"Waiting {startup_delay} seconds for services to be ready...")
        time.sleep(startup_delay)


def main():
    """Main entry point with error handling."""
    try:
        logger.info("Starting RMIT Connect application...")

        # Wait for services to be ready
        wait_for_startup()

        # Import and initialize the application
        from main import application

        logger.info("Application initialized successfully")
        return application

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    app = main()
    # This won't be reached when run by gunicorn
    logger.info("Application ready for gunicorn")

# Make app available for gunicorn
application = main()
