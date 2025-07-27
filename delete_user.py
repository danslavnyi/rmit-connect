#!/usr/bin/env python3
"""
Safe User Deletion Script for RMIT Connect
This script allows you to safely delete users and their related data
"""

from app import app, db
from models import User, Like, Swipe
import sys


def list_all_users():
    """Display all users in the database"""
    print("\n📋 ALL USERS IN DATABASE:")
    print("-" * 50)
    users = User.query.all()
    if not users:
        print("No users found in database.")
        return

    for user in users:
        print(f"ID: {user.id} | Email: {user.email} | Name: {user.name}")
    print("-" * 50)


def get_user_details(user_id):
    """Get detailed information about a user and their connections"""
    user = User.query.get(user_id)
    if not user:
        print(f"❌ User with ID {user_id} not found!")
        return None

    print(f"\n👤 USER DETAILS:")
    print(f"ID: {user.id}")
    print(f"Email: {user.email}")
    print(f"Name: {user.name}")
    print(f"WhatsApp: {user.whatsapp or 'Not provided'}")
    print(f"Instagram: {user.instagram or 'Not provided'}")
    print(f"Created: {user.created_at}")

    # Check related data
    likes_given = Like.query.filter_by(liker_id=user.id).count()
    likes_received = Like.query.filter_by(liked_id=user.id).count()
    swipes = Swipe.query.filter((Swipe.swiper_id == user.id) | (
        Swipe.swiped_id == user.id)).count()

    print(f"\n🔗 CONNECTIONS:")
    print(f"Likes given: {likes_given}")
    print(f"Likes received: {likes_received}")
    print(f"Swipes: {swipes}")

    return user


def delete_user_safely(user_id):
    """Safely delete a user and all related data"""
    user = User.query.get(user_id)
    if not user:
        print(f"❌ User with ID {user_id} not found!")
        return False

    print(f"\n🗑️ DELETING USER: {user.email}")

    try:
        # Delete related data first
        print("Deleting likes...")
        Like.query.filter((Like.liker_id == user_id) |
                          (Like.liked_id == user_id)).delete()

        print("Deleting swipes...")
        Swipe.query.filter((Swipe.swiper_id == user_id) |
                           (Swipe.swiped_id == user_id)).delete()

        # Delete the user
        print("Deleting user...")
        db.session.delete(user)

        # Commit all changes
        db.session.commit()
        print(f"✅ Successfully deleted user: {user.email}")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting user: {str(e)}")
        return False


def main():
    """Main interactive menu"""
    with app.app_context():
        while True:
            print("\n" + "="*50)
            print("🔧 RMIT CONNECT - USER MANAGEMENT")
            print("="*50)
            print("1. List all users")
            print("2. View user details")
            print("3. Delete user")
            print("4. Exit")
            print("-" * 50)

            choice = input("Enter your choice (1-4): ").strip()

            if choice == '1':
                list_all_users()

            elif choice == '2':
                try:
                    user_id = int(input("Enter user ID to view: "))
                    get_user_details(user_id)
                except ValueError:
                    print("❌ Please enter a valid number!")

            elif choice == '3':
                try:
                    user_id = int(input("Enter user ID to delete: "))
                    user = get_user_details(user_id)
                    if user:
                        confirm = input(
                            f"\n⚠️ Are you sure you want to DELETE {user.email}? (yes/no): ").lower()
                        if confirm == 'yes':
                            delete_user_safely(user_id)
                        else:
                            print("❌ Deletion cancelled.")
                except ValueError:
                    print("❌ Please enter a valid number!")

            elif choice == '4':
                print("👋 Goodbye!")
                break

            else:
                print("❌ Invalid choice! Please enter 1-4.")


if __name__ == "__main__":
    main()
