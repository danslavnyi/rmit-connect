#!/bin/bash
# Render deployment start script for RMIT Connect

# Set up environment
export FLASK_ENV=production
export PYTHON_UNBUFFERED=1

echo "Starting RMIT Connect application..."
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "Files in directory: $(ls -la)"

# Start the application with gunicorn
exec gunicorn --config gunicorn_config.py main:application
