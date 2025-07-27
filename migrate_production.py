#!/usr/bin/env python3
"""
Production Database Migration Script
Creates all necessary tables for RMIT Connect in production environment
"""

import os
from app import app, db
from models import User, Like, Swipe, PermanentLoginLink


def create_production_database():
    """Initialize production database with all tables"""
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            print("✅ Production database tables created successfully!")

            # Verify tables exist
            tables = db.engine.table_names() if hasattr(db.engine, 'table_names') else []
            expected_tables = ['users', 'like',
                               'swipe', 'permanent_login_link']

            print(f"📊 Database tables created:")
            for table in expected_tables:
                if hasattr(db.metadata.tables, table) or table in str(db.metadata.tables):
                    print(f"   ✅ {table}")
                else:
                    print(f"   ❌ {table} - MISSING!")

            print(f"🚀 Production database is ready!")
            print(
                f"🌍 Environment: {os.environ.get('FLASK_ENV', 'development')}")
            print(
                f"📡 Database URL: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')[:50]}...")

        except Exception as e:
            print(f"❌ Error creating production database: {str(e)}")
            raise


def check_database_status():
    """Check production database status"""
    with app.app_context():
        try:
            # Test database connection
            user_count = User.query.count()
            like_count = Like.query.count()
            swipe_count = Swipe.query.count()
            link_count = PermanentLoginLink.query.count()

            print(f"📊 Production Database Status:")
            print(f"   👥 Users: {user_count}")
            print(f"   ❤️  Likes: {like_count}")
            print(f"   👆 Swipes: {swipe_count}")
            print(f"   🔗 Login Links: {link_count}")

        except Exception as e:
            print(f"❌ Database connection error: {str(e)}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check_database_status()
    else:
        create_production_database()
        check_database_status()
