from app import app, db, mail
from models import User, PermanentLoginLink, Like, Swipe
from email_templates import get_login_email_html, get_like_notification_email_html
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, abort, jsonify, make_response, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, exists, text
from sqlalchemy.orm import aliased
from security import require_rate_limit, SecurityUtils
from flask_mail import Message
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import re
import time
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
import io
import glob

# Cache control constants
CACHE_MAX_AGE_ONE_YEAR = 31536000  # 1 year in seconds


def get_mutual_matches(user_id):
    """Get mutual matches for a user - optimized query"""
    # Find users who liked current user AND current user liked them back
    # Create a separate alias for the subquery to avoid correlation issues
    like_back = db.aliased(Like)

    return db.session.query(User).join(
        Like, Like.liker_id == User.id
    ).filter(
        Like.liked_id == user_id,
        exists().where(
            and_(
                like_back.liker_id == user_id,
                like_back.liked_id == User.id
            )
        )
    ).all()


def get_liked_by_users(user_id):
    """Get users who liked the current user but not mutual matches"""
    # Get users who liked current user but current user hasn't liked them back
    # Create a separate alias for the subquery to avoid correlation issues
    like_back = db.aliased(Like)

    return db.session.query(User).join(
        Like, Like.liker_id == User.id
    ).filter(
        Like.liked_id == user_id,
        ~exists().where(
            and_(
                like_back.liker_id == user_id,
                like_back.liked_id == User.id
            )
        )
    ).all()


def validate_user_input(email):
    """
    Consolidated input validation for email address.
    Returns (is_valid, cleaned_email_or_error_message)
    """
    # Basic email validation
    if not email or '@' not in email or len(email) < 5:
        return False, "Please enter a valid email address."
    # Further cleaning (strip spaces, lowercase)
    cleaned_email = email.strip().lower()
    # Optionally, add more validation here
    return True, cleaned_email


def send_login_email(email, login_url):
    """Send login email using Flask-Mail or SMTP fallback"""
    try:
        # Try Flask-Mail first (if configured)
        if app.config.get('MAIL_USERNAME'):
            msg = Message(
                'Your RMIT Connect Login Link',
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[email]
            )
            msg.html = get_login_email_html(login_url)
            mail.send(msg)
            return True, "Email sent successfully via Flask-Mail"

    except Exception as e:
        app.logger.error(f"Flask-Mail error: {str(e)}")

    # Fallback to direct SMTP
    try:
        # Get credentials from environment variables
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_username = os.environ.get('SMTP_USERNAME')
        smtp_password = os.environ.get('SMTP_PASSWORD')

        if not smtp_username or not smtp_password:
            return False, "Email credentials not configured"

        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Your RMIT Connect Login Link'
        msg['From'] = smtp_username
        msg['To'] = email

        # Attach HTML content
        html_part = MIMEText(get_login_email_html(login_url), 'html')
        msg.attach(html_part)

        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()

        return True, "Email sent successfully via SMTP"

    except Exception as e:
        app.logger.error(f"SMTP error: {str(e)}")
        return False, f"Failed to send email: {str(e)}"


def send_like_notification_email(user, liker):
    """Send email notification when a user receives a like"""
    try:
        app.logger.info(f"Sending like notification email to: {user.email}")
        # Prepare the email content
        subject = "You've received a new like!"
        sender = app.config['MAIL_DEFAULT_SENDER']
        recipients = [user.email]

        # Use the email template from liked_email_user.py
        body = get_like_notification_email_html(liker, user)

        # Try Flask-Mail first (if configured)
        if app.config.get('MAIL_USERNAME'):
            msg = Message(
                subject,
                sender=sender,
                recipients=recipients
            )
            msg.html = body
            mail.send(msg)
            return True, "Like notification email sent successfully via Flask-Mail"

    except Exception as e:
        app.logger.error(f"Flask-Mail error: {str(e)}")

    # Fallback to direct SMTP
    try:
        # Get credentials from environment variables
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_username = os.environ.get('SMTP_USERNAME')
        smtp_password = os.environ.get('SMTP_PASSWORD')

        if not smtp_username or not smtp_password:
            return False, "Email credentials not configured"

        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_username
        msg['To'] = user.email

        # Attach HTML content
        html_part = MIMEText(body, 'html')
        msg.attach(html_part)

        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()

        return True, "Like notification email sent successfully via SMTP"

    except Exception as e:
        app.logger.error(f"SMTP error: {str(e)}")
        return False, f"Failed to send like notification email: {str(e)}"


def cleanup_temp_files(upload_folder):
    """Clean up temporary files older than 1 hour"""
    try:
        temp_pattern = os.path.join(upload_folder, "temp_*")
        current_time = time.time()

        for temp_file in glob.glob(temp_pattern):
            # Remove files older than 1 hour
            if os.path.exists(temp_file) and (current_time - os.path.getmtime(temp_file)) > 3600:
                os.remove(temp_file)
                app.logger.info(f"Cleaned up temporary file: {temp_file}")
    except Exception as e:
        app.logger.error(f"Error cleaning up temp files: {str(e)}")


def validate_image_file(file):
    """Validate uploaded image file"""
    try:
        # Check file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            return False, f"File type {file_ext} not allowed. Please use: {', '.join(allowed_extensions)}"

        # Check file size (max 5MB)
        if file.content_length and file.content_length > 5 * 1024 * 1024:
            return False, "File size too large. Maximum size is 5MB."

        # Try to open image to validate it's actually an image
        try:
            with Image.open(file.stream) as img:
                img.verify()
            file.stream.seek(0)  # Reset stream position
        except Exception:
            return False, "Invalid image file. Please upload a valid image."

        return True, "Image file is valid"

    except Exception as e:
        return False, f"Error validating image: {str(e)}"


@app.route('/')
def index():
    """Home page - shows different content based on authentication status"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
@require_rate_limit(max_requests=10, window=300)
def login():
    """Email-only login page with security enhancements"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Validate input
        is_valid, result = validate_user_input(email)
        if not is_valid:
            flash(result, 'danger')
            return render_template('login.html')

        email = result

        # Find or create user
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email)
            db.session.add(user)
            try:
                db.session.commit()
                flash('Welcome! A new account has been created for you.', 'info')
            except IntegrityError:
                db.session.rollback()
                flash('An error occurred creating your account.', 'danger')
                return render_template('login.html')

        # Create or get permanent login link
        permanent_link = PermanentLoginLink.create_or_get_link(user.id)
        base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
        login_url = f"{base_url}/auth/{permanent_link.token}"

        # Send login email
        success, message = send_login_email(email, login_url)

        if success:
            flash('Login link has been sent to your email!', 'success')
            flash('Check your inbox for your permanent login link.', 'info')
        else:
            flash('Email service temporarily unavailable.', 'warning')
            flash(f'Your login link: {login_url}', 'info')
            app.logger.warning(f"Email sending failed: {message}")

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
@require_rate_limit(max_requests=10, window=300)
def signup():
    """Signup page - creates account and sends login email"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Validate input
        is_valid, result = validate_user_input(email)
        if not is_valid:
            flash(result, 'danger')
            return render_template('signup.html')

        email = result

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with this email already exists! Check your email for your login link, or use the login page.', 'info')
            # Still send them a login link
            permanent_link = PermanentLoginLink.create_or_get_link(
                existing_user.id)
            base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
            login_url = f"{base_url}/auth/{permanent_link.token}"

            success, message = send_login_email(email, login_url)
            if success:
                flash('Login link has been sent to your email!', 'success')
            return render_template('signup.html')

        # Create new user
        user = User(email=email)
        db.session.add(user)
        try:
            db.session.commit()
            flash(
                '🎉 Welcome to CampusConnect! Your account has been created successfully.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('An error occurred creating your account. Please try again.', 'danger')
            return render_template('signup.html')

        # Create permanent login link and send email
        permanent_link = PermanentLoginLink.create_or_get_link(user.id)
        base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
        login_url = f"{base_url}/auth/{permanent_link.token}"

        success, message = send_login_email(email, login_url)

        if success:
            flash('🚀 Login link has been sent to your email!', 'success')
            flash('📧 Check your inbox to access your new CampusConnect account.', 'info')
        else:
            flash('Account created, but there was an issue sending the email.', 'warning')
            flash(f'Your login link: {login_url}', 'info')
            app.logger.warning(
                f"Email sending failed for new user {email}: {message}")

        return render_template('signup.html')

    return render_template('signup.html')


@app.route('/auth/<token>')
def permanent_login(token):
    """Login using a permanent token from email link"""
    if current_user.is_authenticated:
        logout_user()

    # Find the permanent login link
    permanent_link = PermanentLoginLink.query.filter_by(token=token).first()

    if not permanent_link:
        flash('Invalid login link. Please request a new one.', 'danger')
        return redirect(url_for('login'))

    if not permanent_link.is_valid():
        flash('This login link has been deactivated. Please request a new one.', 'warning')
        return redirect(url_for('login'))

    # Update last used timestamp
    permanent_link.use_link()

    # Update last login time
    user = permanent_link.user
    user.last_login = datetime.utcnow()
    db.session.commit()

    # Log in user
    login_user(user, remember=True)

    # Check if user needs to complete profile
    if not user.profile_completed:
        flash('Welcome to CampusConnect! Please complete your profile to start connecting with other students.', 'info')
        return redirect(url_for('profile'))

    flash(f'Welcome back, {user.name or user.email}!', 'success')

    # Redirect to next page or dashboard
    next_page = request.args.get('next')
    if next_page:
        return redirect(next_page)
    return redirect(url_for('dashboard'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile creation/editing page"""
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        age = request.form.get('age', '').strip()
        education = request.form.get('education', '').strip()
        interests = request.form.get('interests', '').strip()
        country = request.form.get('country', '').strip()

        # Handle dynamic contact fields
        contact_type = request.form.get('contact_type', '').strip()
        contact_value = request.form.get('contact_value', '').strip()

        # Validate required fields
        validation_errors = []
        if not name:
            validation_errors.append('Name is required')
        if not age:
            validation_errors.append('Age is required')
        elif not age.isdigit() or int(age) < 13 or int(age) > 120:
            validation_errors.append('Age must be between 13 and 120')
        if not education:
            validation_errors.append('Education is required')
        if not country:
            validation_errors.append('Country is required')

        if validation_errors:
            for error in validation_errors:
                flash(error, 'danger')
            return redirect(url_for('dashboard'))

        # Update user profile
        current_user.name = name
        current_user.age = int(age)
        current_user.education = education
        current_user.interests = interests
        current_user.country = country

        # Handle contact information storage
        if contact_type == 'phone':
            current_user.phone_number = contact_value
            current_user.instagram = None
        elif contact_type == 'instagram':
            current_user.instagram = contact_value
            current_user.phone_number = None

        # Mark profile as completed only if all required fields are filled
        if name and age and education and country:
            current_user.profile_completed = True

        db.session.commit()

        flash('Your profile has been updated successfully.', 'success')
        return redirect(url_for('dashboard'))

    # GET request - redirect to dashboard (modal will handle profile editing)
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard - requires authentication"""

    # Check if user is new (has incomplete profile)
    is_new_user = current_user.is_new_user()

    # Get mutual matches and liked by users using optimized functions
    mutual_matches = get_mutual_matches(current_user.id)
    liked_by = get_liked_by_users(current_user.id)

    return render_template('dashboard.html',
                           user=current_user,
                           mutual_matches=mutual_matches,
                           liked_by=liked_by,
                           is_new_user=is_new_user)


@app.route('/history')
@login_required
def history():
    """View user's swipe and like history."""
    if not current_user.profile_completed:
        return redirect(url_for('profile'))

    # Get all swipes made by current user
    user_swipes = db.session.query(Swipe, User).join(
        User, Swipe.swiped_id == User.id
    ).filter(
        Swipe.swiper_id == current_user.id
    ).order_by(Swipe.timestamp.desc()).all()

    # Get mutual matches using optimized helper function
    mutual_matches_users = get_mutual_matches(current_user.id)
    mutual_match_user_ids = [user.id for user in mutual_matches_users]

    # Create tuples for template compatibility
    mutual_matches = [(None, user) for user in mutual_matches_users]

    # Get all likes given by current user (excluding mutual matches)
    user_likes_query = db.session.query(Like, User).join(
        User, Like.liked_id == User.id
    ).filter(
        Like.liker_id == current_user.id
    )
    if mutual_match_user_ids:
        user_likes_query = user_likes_query.filter(
            ~Like.liked_id.in_(mutual_match_user_ids))
    user_likes = user_likes_query.order_by(Like.timestamp.desc()).all()

    # Get all likes received by current user (excluding mutual matches)
    received_likes_query = db.session.query(Like, User).join(
        User, Like.liker_id == User.id
    ).filter(
        Like.liked_id == current_user.id
    )
    if mutual_match_user_ids:
        received_likes_query = received_likes_query.filter(
            ~Like.liker_id.in_(mutual_match_user_ids))
    received_likes = received_likes_query.order_by(Like.timestamp.desc()).all()

    # Calculate statistics efficiently
    swipe_likes = sum(1 for s in user_swipes if s[0].action == 'like')
    swipe_declines = len(user_swipes) - swipe_likes

    stats = {
        'total_swipes': len(user_swipes),
        'likes_given': len(user_likes),
        'likes_received': len(received_likes),
        'swipe_likes': swipe_likes,
        'swipe_declines': swipe_declines,
        'mutual_matches': len(mutual_matches_users)
    }

    return render_template('history.html',
                           user_swipes=user_swipes,
                           user_likes=user_likes,
                           received_likes=received_likes,
                           mutual_matches=mutual_matches,
                           stats=stats)


@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))


@app.route('/explore')
@login_required
def explore():
    """Explore page - discover other users (Tinder-style)"""
    if not current_user.profile_completed:
        return redirect(url_for('profile'))

    # Initialize session-based seen users list
    if 'session_seen_users' not in session:
        session['session_seen_users'] = []

    # Get users that have been liked and mutual connections
    liked_ids = [l.liked_id for l in Like.query.filter_by(
        liker_id=current_user.id)]
    mutual_connection_ids = [u.id for u in get_mutual_matches(current_user.id)]

    # Get total available users count
    total_available = User.query.filter(
        User.id != current_user.id,
        User.profile_completed == True
    ).count()

    # Adaptive buffer sizes based on user base
    if total_available <= 5:
        recent_buffer_size, session_buffer_size = 1, 2
        flash('Small user base - showing more variety', 'info')
    elif total_available <= 10:
        recent_buffer_size, session_buffer_size = 3, 5
    elif total_available <= 20:
        recent_buffer_size, session_buffer_size = 8, 8
    else:
        recent_buffer_size, session_buffer_size = 20, 10

    # Get recently swiped user IDs
    recent_swiped_user_ids = [s.swiped_id for s in Swipe.query.filter_by(
        swiper_id=current_user.id).order_by(Swipe.timestamp.desc()).limit(recent_buffer_size)]

    # Get session seen users
    session_seen_ids = session['session_seen_users'][-session_buffer_size:
                                                     ] if session['session_seen_users'] else []

    # Combine all excluded users
    excluded_users = list(set(liked_ids + mutual_connection_ids +
                          recent_swiped_user_ids + session_seen_ids + [current_user.id]))

    # Try to find a user not in the excluded list
    user = User.query.filter(
        User.id.notin_(excluded_users),
        User.profile_completed == True
    ).order_by(db.func.random()).first()

    # Fallback strategies if no fresh users
    if not user and total_available > 3:
        fallback_buffer_size = max(1, recent_buffer_size // 3)
        last_few_swiped_ids = [s.swiped_id for s in Swipe.query.filter_by(
            swiper_id=current_user.id).order_by(Swipe.timestamp.desc()).limit(fallback_buffer_size)]

        excluded_less_strict = list(
            set(liked_ids + mutual_connection_ids + last_few_swiped_ids + [current_user.id]))
        user = User.query.filter(
            User.id.notin_(excluded_less_strict),
            User.profile_completed == True
        ).order_by(db.func.random()).first()

    # Allow old declined users
    if not user:
        decline_offset = max(5, recent_buffer_size // 2)
        old_declined_ids = [s.swiped_id for s in Swipe.query.filter_by(
            swiper_id=current_user.id, action='decline'
        ).order_by(Swipe.timestamp.desc()).offset(decline_offset).all()]

        excluded_for_old = list(
            set(liked_ids + mutual_connection_ids + [current_user.id]))
        user = User.query.filter(
            User.id.in_(old_declined_ids),
            User.id.notin_(excluded_for_old),
            User.profile_completed == True
        ).order_by(db.func.random()).first()

        if user:
            flash('Showing previous profiles again - you might change your mind!', 'info')

    # Final fallback
    if not user:
        excluded_final = list(
            set(liked_ids + mutual_connection_ids + [current_user.id]))
        user = User.query.filter(
            User.id.notin_(excluded_final),
            User.profile_completed == True
        ).order_by(db.func.random()).first()

    if not user:
        flash('No other students available to explore at the moment!', 'info')
        return redirect(url_for('dashboard'))

    # Add user to session seen list
    if user.id not in session['session_seen_users']:
        session['session_seen_users'].append(user.id)
        # Keep only last 15
        session['session_seen_users'] = session['session_seen_users'][-15:]
        session.modified = True

    return render_template('explore.html', user=user)


@app.route('/reset_explore_session', methods=['POST'])
@login_required
def reset_explore_session():
    """Reset the session seen users list for explore"""
    session['session_seen_users'] = []
    session.modified = True
    flash('Explore session reset! You\'ll see fresh profiles now.', 'info')
    return redirect(url_for('explore'))


@app.route('/connections')
@login_required
def connections():
    """View mutual connections and manage contact information"""
    if not current_user.profile_completed:
        return redirect(url_for('profile'))

    # Get mutual matches using optimized function
    mutual_matches = get_mutual_matches(current_user.id)

    return render_template('connections.html',
                           user=current_user,
                           mutual_matches=mutual_matches)


@app.route('/update_contact_info', methods=['POST'])
@login_required
def update_contact_info():
    """Update user's contact information"""
    # Get form data
    phone_number = request.form.get('phone_number', '').strip()
    instagram = request.form.get('instagram', '').strip()
    discord = request.form.get('discord', '').strip()
    linkedin = request.form.get('linkedin', '').strip()
    other_contact = request.form.get('other_contact', '').strip()

    # Validate phone number if provided
    if phone_number:
        clean_phone = re.sub(r'[\s\-\(\)\+]', '', phone_number)

        if not clean_phone.isdigit():
            flash('Phone number must contain only numbers and common formatting characters (+, -, spaces, parentheses).', 'error')
            return redirect(url_for('connections'))

        if not (8 <= len(clean_phone) <= 15):
            flash('Phone number must be between 8 and 15 digits long.', 'error')
            return redirect(url_for('connections'))

    # Update user information
    current_user.phone_number = phone_number
    current_user.instagram = instagram
    current_user.discord = discord
    current_user.linkedin = linkedin
    current_user.other_contact = other_contact

    db.session.commit()
    flash('Contact information updated successfully!', 'success')
    return redirect(url_for('connections'))


@app.route('/remove_connection/<int:user_id>', methods=['POST'])
@login_required
def remove_connection(user_id):
    """Remove a mutual connection by deleting both like relationships"""
    # Prevent removing connection with yourself
    if user_id == current_user.id:
        flash('You cannot remove a connection with yourself.', 'warning')
        return redirect(url_for('connections'))

    # Check if there's a mutual connection
    my_like = Like.query.filter_by(
        liker_id=current_user.id, liked_id=user_id).first()
    their_like = Like.query.filter_by(
        liker_id=user_id, liked_id=current_user.id).first()

    if not (my_like and their_like):
        flash('No mutual connection found with this user.', 'warning')
        return redirect(url_for('connections'))

    # Get the user's name for the flash message
    user = User.query.get(user_id)
    user_name = user.name if user else "User"

    # Remove both like relationships to break the connection
    if my_like:
        db.session.delete(my_like)
    if their_like:
        db.session.delete(their_like)

    db.session.commit()

    flash(
        f'Connection with {user_name} has been removed successfully.', 'success')

    # Redirect back to the referring page (history or connections)
    referrer = request.referrer
    if referrer and 'history' in referrer:
        return redirect(url_for('history') + '#interactions')
    else:
        return redirect(url_for('connections'))


@app.route('/like/<int:user_id>', methods=['POST'])
@login_required
@require_rate_limit(max_requests=50, window=300)
def like_user(user_id):
    """Like a user - optimized version"""
    # Input validation
    if not isinstance(user_id, int) or user_id <= 0:
        abort(400)

    if user_id == current_user.id:
        return '', 400

    # Verify target user exists
    target_user = User.query.get(user_id)
    if not target_user:
        abort(404)

    try:
        # Check if already liked
        existing_like = Like.query.filter_by(
            liker_id=current_user.id, liked_id=user_id).first()
        if not existing_like:
            new_like = Like(liker_id=current_user.id, liked_id=user_id)
            db.session.add(new_like)
            send_like_notification_email(target_user, current_user)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in like_user: {str(e)}")
        abort(500)
    return '', 204


@app.route('/unlike/<int:user_id>', methods=['POST'])
@login_required
def unlike_user(user_id):
    """Remove a like from the current user to another user"""
    # Prevent unliking yourself
    if user_id == current_user.id:
        return '', 400

    # Find and remove the like
    existing_like = Like.query.filter_by(
        liker_id=current_user.id, liked_id=user_id).first()

    if existing_like:
        db.session.delete(existing_like)
        db.session.commit()
        flash('Like removed successfully!', 'success')
    else:
        flash('Like not found.', 'warning')

    # Redirect back to history page with the "My Likes" tab active
    return redirect(url_for('history') + '#likes-given')


@app.route('/explore/<int:user_id>')
@login_required
def explore_user(user_id):
    user = User.query.get_or_404(user_id)
    # Get all users who liked current user using the helper function
    liked_by = get_liked_by_users(current_user.id)
    # Find the index of the current user in liked_by
    ids = [u.id for u in liked_by]
    try:
        idx = ids.index(user_id)
        next_liker_id = ids[idx + 1] if idx + 1 < len(ids) else None
    except ValueError:
        next_liker_id = None
    return render_template('explore_single.html', user=user, next_liker_id=next_liker_id)


@app.route('/profile/<int:user_id>')
@login_required
def profile_view(user_id):
    """View a user's profile without action buttons (for history/interactions)"""
    if user_id == current_user.id:
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    return render_template('profile_view.html', user=user)


@app.route('/swipe/<int:user_id>/<action>', methods=['POST'])
@login_required
@require_rate_limit(max_requests=100, window=300)  # 100 swipes per 5 minutes
def swipe(user_id, action):
    # Input validation
    if not isinstance(user_id, int) or user_id <= 0:
        abort(400)

    if action not in ['like', 'decline']:
        abort(400)

    # Sanitize action parameter
    action = SecurityUtils.sanitize_user_input(action)

    # Prevent swiping on yourself
    if user_id == current_user.id:
        return '', 400

    # Verify target user exists
    target_user = User.query.get(user_id)
    if not target_user:
        abort(404)

    try:
        # Check if already swiped - if so, remove the old swipe to allow re-swiping
        existing = Swipe.query.filter_by(
            swiper_id=current_user.id, swiped_id=user_id).first()
        if existing:
            # Remove old swipe to allow re-evaluation
            db.session.delete(existing)

        # Add new swipe record
        db.session.add(Swipe(swiper_id=current_user.id,
                       swiped_id=user_id, action=action))

        # If it's a like, also add to likes table
        if action == 'like':
            existing_like = Like.query.filter_by(
                liker_id=current_user.id, liked_id=user_id).first()
            if not existing_like:
                db.session.add(
                    Like(liker_id=current_user.id, liked_id=user_id))
                send_like_notification_email(target_user, current_user)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in swipe: {str(e)}")
        abort(500)

    return '', 204


@app.route('/upload_profile_image', methods=['POST'])
@login_required
@require_rate_limit(max_requests=10, window=300)  # 10 uploads per 5 minutes
def upload_profile_image():
    """Upload and process profile image"""
    try:
        # Check if file was uploaded
        if 'profile_image' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['profile_image']

        # Check if file is empty
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        # Validate image file using our validation function
        is_valid, error_message = validate_image_file(file)
        if not is_valid:
            return jsonify({'success': False, 'error': error_message}), 400

        # Generate secure filename
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        secure_name = f"user_{current_user.id}_{uuid.uuid4().hex[:8]}.{file_extension}"

        # Get upload folder
        upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))

        # Ensure upload folder exists
        os.makedirs(upload_folder, exist_ok=True)

        # Clean up old temporary files
        cleanup_temp_files(upload_folder)

        # Save original file temporarily
        temp_file_path = os.path.join(upload_folder, f"temp_{secure_name}")
        file.save(temp_file_path)

        # Get original file size for compression comparison
        file_size = os.path.getsize(temp_file_path)

        # Process image for optimization and compression
        try:
            with Image.open(temp_file_path) as img:
                # Only convert to RGB if absolutely necessary (for JPEG output)
                # This preserves original colors better
                original_mode = img.mode
                app.logger.info(
                    f"Processing image: {secure_name}, Original mode: {original_mode}, Size: {img.size}")

                # Calculate optimal dimensions (max 600x600 for better performance)
                max_size = (600, 600)
                original_size = img.size

                # Resize if image is too large
                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    app.logger.info(
                        f"Resized image from {original_size} to {img.size}")

                # Determine optimal format and quality based on original
                if file_extension.lower() in ['jpg', 'jpeg']:
                    # For JPEG, convert to RGB only if needed
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    output_format = 'JPEG'
                    quality = 95  # Maximum quality to preserve colors
                    optimize = True
                elif file_extension.lower() == 'png':
                    # For PNG, keep original mode if possible, only convert to RGB for JPEG output
                    if img.mode not in ('RGB', 'L', 'RGBA'):
                        img = img.convert('RGB')
                    elif img.mode == 'RGBA':
                        # Convert RGBA to RGB with white background to preserve colors
                        background = Image.new(
                            'RGB', img.size, (255, 255, 255))
                        # Use alpha channel as mask
                        background.paste(img, mask=img.split()[-1])
                        img = background
                        app.logger.info(
                            f"Converted RGBA to RGB with white background")
                    output_format = 'JPEG'
                    quality = 95  # Maximum quality to preserve colors
                    optimize = True
                    secure_name = secure_name.rsplit('.', 1)[0] + '.jpg'
                elif file_extension.lower() == 'webp':
                    # Keep WebP format with original colors
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGB')
                    output_format = 'WEBP'
                    quality = 95  # Maximum quality for WebP
                    optimize = True
                else:
                    # For other formats, convert to RGB only if needed
                    if img.mode not in ('RGB', 'L'):
                        if img.mode == 'RGBA':
                            # Convert RGBA to RGB with white background to preserve colors
                            background = Image.new(
                                'RGB', img.size, (255, 255, 255))
                            # Use alpha channel as mask
                            background.paste(img, mask=img.split()[-1])
                            img = background
                            app.logger.info(
                                f"Converted RGBA to RGB with white background")
                        else:
                            img = img.convert('RGB')
                    output_format = 'JPEG'
                    quality = 95  # Maximum quality to preserve colors
                    optimize = True
                    secure_name = secure_name.rsplit('.', 1)[0] + '.jpg'

                app.logger.info(
                    f"Final image mode: {img.mode}, Format: {output_format}, Quality: {quality}%")

                # Debug: Check if image has colors
                if img.mode == 'RGB':
                    # Sample a few pixels to verify colors
                    sample_pixels = [
                        img.getpixel((0, 0)),
                        img.getpixel((img.width//2, img.height//2)),
                        img.getpixel((img.width-1, img.height-1))
                    ]
                    app.logger.info(f"Sample pixel colors: {sample_pixels}")

                # Save optimized image
                final_file_path = os.path.join(upload_folder, secure_name)
                img.save(final_file_path, output_format,
                         quality=quality, optimize=optimize)

                # Remove temporary file
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

                # Get final file size for logging
                final_size = os.path.getsize(final_file_path)
                compression_ratio = (1 - (final_size / file_size)) * 100

                app.logger.info(
                    f"Image compressed: {file_size} bytes -> {final_size} bytes ({compression_ratio:.1f}% reduction)")
                app.logger.info(
                    f"Image mode: {original_mode} -> {img.mode}, Quality: {quality}%")

        except Exception as e:
            app.logger.error(f"Error processing image {secure_name}: {str(e)}")
            app.logger.error(
                f"Image mode was: {img.mode if 'img' in locals() else 'unknown'}")
            # If processing fails, use original file but rename it
            if os.path.exists(temp_file_path):
                os.rename(temp_file_path, os.path.join(
                    upload_folder, secure_name))
            else:
                return jsonify({'success': False, 'error': 'Failed to process image'}), 500

        # Update user's profile image in database
        current_user.profile_image = secure_name
        db.session.commit()

        return jsonify({
            'success': True,
            'image_url': current_user.get_profile_image_url(),
            'message': 'Profile image updated successfully!'
        })

    except Exception as e:
        app.logger.error(f"Error uploading profile image: {str(e)}")
        return jsonify({'success': False, 'error': 'An error occurred while uploading the image'}), 500


# Performance and SEO routes
@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    start_time = time.time()
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'

    response_time = (time.time() - start_time) * 1000  # in milliseconds

    return jsonify({
        'status': 'healthy' if db_status == 'ok' else 'unhealthy',
        'database': db_status,
        'response_time_ms': round(response_time, 2),
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt for SEO"""
    response = make_response(send_from_directory(
        app.static_folder, 'robots.txt'))
    response.headers['Content-Type'] = 'text/plain'
    return response


@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html',
                           title='Page Not Found',
                           content='<div class="text-center"><h1>404</h1><p>Page not found.</p></div>'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html',
                           title='Server Error',
                           content='<div class="text-center"><h1>500</h1><p>Internal server error.</p></div>'), 500


@app.route('/debug_image/<filename>')
def debug_image(filename):
    """Debug route to check uploaded image properties"""
    try:
        upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
        file_path = os.path.join(upload_folder, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404

        with Image.open(file_path) as img:
            # Get image properties
            info = {
                'mode': img.mode,
                'size': img.size,
                'format': img.format,
                'filename': filename,
                'file_size': os.path.getsize(file_path)
            }

            # Sample some pixels to check colors
            if img.mode == 'RGB':
                sample_pixels = [
                    img.getpixel((0, 0)),
                    img.getpixel((img.width//2, img.height//2)),
                    img.getpixel((img.width-1, img.height-1))
                ]
                info['sample_pixels'] = sample_pixels

                # Check if image is grayscale (all R=G=B)
                is_grayscale = all(r == g == b for r, g, b in sample_pixels)
                info['is_grayscale'] = is_grayscale

            return jsonify(info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files securely with optimized delivery"""
    try:
        uploads_folder = app.config.get('UPLOAD_FOLDER', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
        default_image = 'default-profile.png'
        file_path = os.path.join(uploads_folder, filename)

        # Check if requested file exists
        if not os.path.exists(file_path):
            # Fallback to default image if requested file does not exist
            app.logger.warning(
                f"Requested image '{filename}' not found, serving default image.")

            # Try to serve default image from static/images folder
            static_images_folder = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
            default_file_path = os.path.join(
                static_images_folder, default_image)

            if os.path.exists(default_file_path):
                response = send_from_directory(
                    static_images_folder,
                    default_image,
                    conditional=True
                )
                response.cache_control.max_age = CACHE_MAX_AGE_ONE_YEAR
                response.cache_control.public = True
                return response
            else:
                app.logger.error(
                    f"Default image '{default_image}' not found in static/images folder.")
                abort(404)

        # Serve the requested file
        response = send_from_directory(
            uploads_folder,
            filename,
            conditional=True
        )
        response.cache_control.max_age = CACHE_MAX_AGE_ONE_YEAR
        response.cache_control.public = True

        # Set proper content type based on file extension
        if filename.lower().endswith('.webp'):
            response.headers['Content-Type'] = 'image/webp'
        elif filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            response.headers['Content-Type'] = 'image/jpeg'
        elif filename.lower().endswith('.png'):
            response.headers['Content-Type'] = 'image/png'
        elif filename.lower().endswith('.gif'):
            response.headers['Content-Type'] = 'image/gif'

        return response
    except Exception as e:
        app.logger.error(f"Error serving file {filename}: {str(e)}")
        abort(404)


@app.route('/uploads/<base_filename>/<size>')
def uploaded_file_sized(base_filename, size):
    """Serve different sized versions of uploaded images"""
    try:
        # Validate size parameter
        valid_sizes = ['thumbnail', 'medium', 'large']
        if size not in valid_sizes:
            abort(400)

        # Generate sized filename
        if size == 'large':
            filename = base_filename
        else:
            name_part = base_filename.rsplit('.', 1)[0]
            filename = f"{name_part}_{size}.webp"

        return uploaded_file(filename)

    except Exception as e:
        app.logger.error(
            f"Error serving sized file {base_filename}/{size}: {str(e)}")
        abort(404)


@app.route('/profile-image/<int:user_id>')
def get_user_profile_image(user_id):
    """Get user profile image with robust fallback handling"""
    try:
        user = User.query.get(user_id)
        if not user:
            abort(404)

        # Get the profile image URL
        image_url = user.get_profile_image_url()

        # If it's a default image, serve it directly
        if image_url == "/static/images/default-profile.png":
            static_images_folder = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
            return send_from_directory(
                static_images_folder,
                'default-profile.png',
                conditional=True
            )

        # Otherwise, redirect to the uploads route
        return redirect(image_url)

    except Exception as e:
        app.logger.error(
            f"Error serving profile image for user {user_id}: {str(e)}")
        # Fallback to default image
        static_images_folder = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
        return send_from_directory(
            static_images_folder,
            'default-profile.png',
            conditional=True
        )
