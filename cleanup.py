#!/usr/bin/env python3
"""
Code Cleanup Script for RMIT Connect
Removes redundant files and cleans up the codebase
"""

import os
import shutil


def cleanup_files():
    """Remove redundant and test files for production"""

    files_to_remove = [
        'test_email.py',           # Development testing only
        'test_security.py',        # Development testing only
        'setup_email.py',          # One-time setup, not needed in production
        'migrate_db.py',           # Old migration script
        'migrate_profile_images.py',  # One-time migration completed
        '.env.template',           # Redundant with .env.example
        'email_config.sh',         # Not needed
        'replit.md',              # Replit specific
        '.replit'                 # Replit specific
    ]

    print("🧹 Cleaning up redundant files...")

    for file in files_to_remove:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"   ✅ Removed: {file}")
            except Exception as e:
                print(f"   ❌ Failed to remove {file}: {str(e)}")
        else:
            print(f"   ⏭️  Not found: {file}")

    # Clean up empty directories
    dirs_to_check = ['__pycache__']
    for dir_name in dirs_to_check:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"   ✅ Removed directory: {dir_name}")
            except Exception as e:
                print(f"   ❌ Failed to remove {dir_name}: {str(e)}")


def report_cleanup():
    """Report on cleanup status"""
    print("\n📊 Cleanup Summary:")

    # Count remaining Python files
    py_files = [f for f in os.listdir('.') if f.endswith('.py')]
    print(f"   📁 Python files remaining: {len(py_files)}")
    for f in sorted(py_files):
        size = os.path.getsize(f) / 1024  # KB
        print(f"      - {f} ({size:.1f} KB)")

    # Essential files check
    essential_files = [
        'main.py', 'app.py', 'routes.py', 'models.py',
        'config.py', 'security.py', 'requirements.txt',
        'Procfile', 'runtime.txt'
    ]

    print(f"\n✅ Essential files present:")
    for file in essential_files:
        status = "✅" if os.path.exists(file) else "❌"
        print(f"   {status} {file}")


if __name__ == "__main__":
    print("🚀 RMIT Connect - Code Cleanup")
    print("=" * 50)

    cleanup_files()
    report_cleanup()

    print(f"\n🎯 Cleanup complete! Your codebase is now optimized.")
