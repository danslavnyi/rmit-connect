#!/usr/bin/env bash
# Render.com startup script

echo "Starting RMIT Connect production deployment..."

# Create upload directory if it doesn't exist
mkdir -p static/uploads

# Initialize database
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created successfully!')
"

echo "Production setup completed successfully!"
echo "Starting application with Gunicorn..."

# Start the application
exec gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
