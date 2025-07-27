#!/usr/bin/env python3
"""
RMIT Connect Database Viewer
Quick command-line tool to view all users and database statistics
"""

from app import app, db
from models import User, Like, Swipe, PermanentLoginLink
from datetime import datetime
from sqlalchemy import func


def print_separator(title, width=80):
    """Print a formatted separator with title"""
    print("=" * width)
    print(f" {title} ".center(width))
    print("=" * width)


def print_user_info(user, index, total):
    """Print detailed information about a user"""
    print(f"\n🔹 USER #{user.id} ({index}/{total})")
    print(f"   Name: {user.name or '❌ Not set'}")
    print(f"   Email: {user.email}")
    print(f"   Age: {user.age or '❌ Not set'}")
    print(f"   Education: {user.education or '❌ Not set'}")
    print(f"   Country: {user.country or '❌ Not set'}")

    # Interests (truncated if too long)
    interests = user.interests or '❌ Not set'
    if len(interests) > 60:
        interests = interests[:60] + "..."
    print(f"   Interests: {interests}")

    # Profile status
    print(f"   Profile Image: {'✅ Yes' if user.profile_image else '❌ No'}")
    print(
        f"   Profile Complete: {'✅ Yes' if user.profile_completed else '❌ No'}")

    # Contact info
    contacts = []
    if user.whatsapp:
        contacts.append(f"📱 WhatsApp: {user.whatsapp}")
    if user.instagram:
        contacts.append(f"📸 Instagram: {user.instagram}")
    if user.discord:
        contacts.append(f"🎮 Discord: {user.discord}")
    if user.linkedin:
        contacts.append(f"💼 LinkedIn: {user.linkedin}")

    print(f"   Contact Info: {'; '.join(contacts) if contacts else '❌ None'}")
    print(
        f"   Joined: {user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else '❓ Unknown'}")

    # User activity
    likes_given = Like.query.filter_by(liker_id=user.id).count()
    likes_received = Like.query.filter_by(liked_id=user.id).count()
    swipes = Swipe.query.filter_by(swiper_id=user.id).count()

    print(
        f"   Activity: ❤️ {likes_given} likes given, 💝 {likes_received} likes received, 👆 {swipes} total swipes")


def view_database_stats():
    """Display comprehensive database statistics"""
    with app.app_context():
        print_separator("🗄️ RMIT CONNECT DATABASE VIEWER")

        # Basic statistics
        total_users = User.query.count()
        completed_profiles = User.query.filter_by(
            profile_completed=True).count()
        users_with_photos = User.query.filter(
            User.profile_image.isnot(None)).count()
        total_likes = Like.query.count()
        total_swipes = Swipe.query.count()
        total_login_links = PermanentLoginLink.query.count()

        # Calculate mutual matches (connections)
        mutual_matches = db.session.query(Like.liker_id).join(
            Like,
            (Like.liker_id == Like.liked_id) & (Like.liked_id == Like.liker_id)
        ).distinct().count()

        print(f"\n📊 DATABASE STATISTICS:")
        print(f"├── 👥 Total Users: {total_users}")
        print(f"├── ✅ Completed Profiles: {completed_profiles} ({(completed_profiles/total_users*100):.1f}%)" if total_users >
              0 else "├── ✅ Completed Profiles: 0")
        print(f"├── 📸 Users with Photos: {users_with_photos}")
        print(f"├── ❤️  Total Likes: {total_likes}")
        print(f"├── 👆 Total Swipes: {total_swipes}")
        print(f"├── 💝 Mutual Connections: {mutual_matches}")
        print(f"└── 🔗 Login Links Created: {total_login_links}")

        # Most active users
        if total_users > 0:
            most_active = db.session.query(
                User.id, User.name, User.email,
                func.count(Swipe.id).label('swipe_count')
            ).outerjoin(Swipe, Swipe.swiper_id == User.id)\
             .group_by(User.id)\
             .order_by(func.count(Swipe.id).desc())\
             .limit(3).all()

            print(f"\n🏆 MOST ACTIVE USERS:")
            for i, (user_id, name, email, swipes) in enumerate(most_active, 1):
                display_name = name or email
                print(f"   {i}. {display_name} - {swipes} swipes")

        return total_users


def view_all_users():
    """Display detailed information about all users"""
    with app.app_context():
        total_users = view_database_stats()

        if total_users == 0:
            print(f"\n❌ No users found in the database.")
            return

        print(f"\n👥 ALL USERS ({total_users} total):")
        print("-" * 80)

        # Get all users ordered by creation date (newest first)
        users = User.query.order_by(User.created_at.desc()).all()

        for i, user in enumerate(users, 1):
            print_user_info(user, i, total_users)


def view_quick_stats():
    """Display just the basic statistics"""
    with app.app_context():
        total_users = view_database_stats()

        if total_users > 0:
            print(
                f"\n🚀 Quick view complete! Use view_all_users() to see detailed user information.")
        else:
            print(
                f"\n💡 No users in database yet. Users will appear here after they sign up.")


def main():
    """Main function with menu options"""
    print("🎯 RMIT Connect Database Viewer")
    print("1. Quick Stats Only")
    print("2. Full User Details")

    choice = input("\nEnter your choice (1 or 2): ").strip()

    if choice == "1":
        view_quick_stats()
    elif choice == "2":
        view_all_users()
    else:
        print("Invalid choice. Showing quick stats...")
        view_quick_stats()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Database viewer closed.")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("Make sure you're running this from your project directory.")
