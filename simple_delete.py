#!/usr/bin/env python3
"""Simple user deletion script - run without Flask app running"""

import sqlite3
import sys


def delete_user_by_id(user_id):
    # Connect directly to SQLite database
    conn = sqlite3.connect('instance/campusconnect.db')
    cursor = conn.cursor()

    try:
        # First, get user info
        cursor.execute(
            "SELECT email, name FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            print(f"❌ User with ID {user_id} not found!")
            return

        email, name = user
        print(f"🗑️ Deleting user: {email} ({name})")

        # Delete related data first
        print("Deleting likes...")
        cursor.execute(
            "DELETE FROM likes WHERE liker_id = ? OR liked_id = ?", (user_id, user_id))

        print("Deleting swipes...")
        cursor.execute(
            "DELETE FROM swipes WHERE swiper_id = ? OR swiped_id = ?", (user_id, user_id))

        # Delete user
        print("Deleting user...")
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))

        # Commit changes
        conn.commit()
        print(f"✅ Successfully deleted user: {email}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        conn.close()


def list_users():
    conn = sqlite3.connect('instance/campusconnect.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, name FROM users ORDER BY id")
    users = cursor.fetchall()

    print("\n📋 ALL USERS:")
    print("-" * 50)
    for user_id, email, name in users:
        print(f"ID: {user_id} | Email: {email} | Name: {name}")
    print("-" * 50)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("User Management Tool")
        print("Usage:")
        print("  python simple_delete.py list              # List all users")
        print("  python simple_delete.py delete <user_id>  # Delete user by ID")
    elif sys.argv[1] == "list":
        list_users()
    elif sys.argv[1] == "delete" and len(sys.argv) == 3:
        try:
            user_id = int(sys.argv[2])
            delete_user_by_id(user_id)
        except ValueError:
            print("❌ Please provide a valid user ID number")
    else:
        print("❌ Invalid command. Use 'list' or 'delete <user_id>'")
