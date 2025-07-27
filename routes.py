from app import app, db, mail
from models import User, PermanentLoginLink, Like, Swipe
from email_templates import get_login_email_html
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, abort, jsonify, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from security import require_rate_limit, SecurityUtils
from flask_mail import Message
from werkzeug.utils import secure_filename
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import uuid


# Upload settings from config
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_image(image_file, user_id):
    """Process and save uploaded image with security checks"""
    if not image_file or not allowed_file(image_file.filename):
        return None, "Invalid file type. Please upload PNG, JPG, JPEG, GIF, or WebP images."

    try:
        # Create unique filename to prevent conflicts
        file_extension = image_file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"user_{user_id}_{uuid.uuid4().hex[:8]}.{file_extension}"

        # Save original file temporarily
        temp_path = os.path.join(
            app.config['UPLOAD_FOLDER'], f"temp_{unique_filename}")
        image_file.save(temp_path)

        # Open and validate image with Pillow
        with Image.open(temp_path) as img:
            # Convert to RGB if necessary (for JPEG compatibility)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Resize image if too large (max 800x800 for profile pics)
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Save processed image
            final_path = os.path.join(
                app.config['UPLOAD_FOLDER'], unique_filename)
            img.save(final_path, optimize=True, quality=85)

        # Remove temporary file
        os.remove(temp_path)

        return unique_filename, "Image uploaded successfully"

    except Exception as e:
        # Clean up temp file if it exists
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None, f"Error processing image: {str(e)}"


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files securely"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


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


@app.route('/')
def index():
    """Home page - shows different content based on authentication status"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
@require_rate_limit(max_requests=10, window=300)  # 10 attempts per 5 minutes
def login():
    """Email-only login page with security enhancements"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Enhanced input validation
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('login.html')

        # Sanitize and validate input length
        # RFC 5321 limit
        if not SecurityUtils.validate_input_length(email, 320):
            flash('Email address too long.', 'danger')
            return render_template('login.html')

        email = SecurityUtils.sanitize_user_input(email)

        # Enhanced email validation
        if not SecurityUtils.validate_email_security(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('login.html')

        # Find or create user
        user = User.query.filter_by(email=email).first()
        if not user:
            # Create new user automatically
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

        # Generate permanent login URL - production safe
        base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
        login_url = f"{base_url}/auth/{permanent_link.token}"

        # Send login email directly using Python
        success, message = send_login_email(email, login_url)

        if success:
            flash('Login link has been sent to your email!', 'success')
            flash('Check your inbox for your permanent login link.', 'info')
        else:
            flash(
                'Error sending email. Please check your email configuration.', 'warning')
            # Fallback: show the link for development/testing
            flash(f'Your permanent login link: {login_url}', 'info')
            app.logger.warning(f"Email sending failed: {message}")

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
@require_rate_limit(max_requests=10, window=300)  # 10 attempts per 5 minutes
def signup():
    """Signup page - creates account and sends login email"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Enhanced input validation
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('signup.html')

        # Sanitize and validate input length
        if not SecurityUtils.validate_input_length(email, 320):
            flash('Email address too long.', 'danger')
            return render_template('signup.html')

        email = SecurityUtils.sanitize_user_input(email)

        # Enhanced email validation
        if not SecurityUtils.validate_email_security(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('signup.html')

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

        # Create permanent login link
        permanent_link = PermanentLoginLink.create_or_get_link(user.id)

        # Generate permanent login URL - production safe
        base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
        login_url = f"{base_url}/auth/{permanent_link.token}"

        # Send welcome email with login link
        success, message = send_login_email(email, login_url)

        if success:
            flash('🚀 Login link has been sent to your email!', 'success')
            flash('📧 Check your inbox to access your new CampusConnect account.', 'info')
        else:
            flash('Account created, but there was an issue sending the email.', 'warning')
            # Fallback: show the link
            flash(f'Your login link: {login_url}', 'info')
            app.logger.warning(
                f"Email sending failed for new user {email}: {message}")

        return render_template('signup.html')

    # GET request - show signup form
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
        # Handle image-only upload (AJAX request from dashboard)
        profile_image_file = request.files.get('profile_image')

        # Check if this is an image-only upload (no other form data)
        if profile_image_file and profile_image_file.filename and not request.form.get('name'):
            image_filename, image_message = process_image(
                profile_image_file, current_user.id)
            if image_filename:
                # Delete old image if it exists
                if current_user.profile_image:
                    old_image_path = os.path.join(
                        app.config['UPLOAD_FOLDER'], current_user.profile_image)
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except:
                            pass  # Ignore errors when deleting old image

                # Update profile image
                current_user.profile_image = image_filename
                db.session.commit()

                # Return JSON response for AJAX
                if request.headers.get('Content-Type', '').startswith('multipart/form-data'):
                    # Simple response that JavaScript can check
                    return f'✅ {image_message}', 200
            else:
                # Return error response
                return f'❌ {image_message}', 400

        # Regular form submission (full profile update)
        # Get form data
        name = request.form.get('name', '').strip()
        age = request.form.get('age', '').strip()
        education = request.form.get('education', '').strip()
        interests = request.form.get('interests', '').strip()
        country = request.form.get('country', '').strip()

        # Handle image upload for full form
        new_image_filename = None

        if profile_image_file and profile_image_file.filename:
            image_filename, image_message = process_image(
                profile_image_file, current_user.id)
            if image_filename:
                new_image_filename = image_filename
                flash(f'✅ {image_message}', 'success')

                # Delete old image if it exists
                if current_user.profile_image:
                    old_image_path = os.path.join(
                        app.config['UPLOAD_FOLDER'], current_user.profile_image)
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except:
                            pass  # Ignore errors when deleting old image
            else:
                flash(f'❌ {image_message}', 'danger')
                return redirect(url_for('dashboard'))

        # Validate required fields
        missing_fields = []
        if not name:
            missing_fields.append('Name')
        if not age:
            missing_fields.append('Age')
        if not education:
            missing_fields.append('Education')
        if not interests:
            missing_fields.append('Interests')
        if not country:
            missing_fields.append('Country')

        if missing_fields:
            flash(
                f'Please fill in the following required fields: {", ".join(missing_fields)}', 'danger')
            return redirect(url_for('dashboard'))

        # Validate age
        try:
            age_int = int(age)
            if age_int < 16 or age_int > 50:
                flash('Age must be between 16 and 50.', 'danger')
                return redirect(url_for('dashboard'))
        except ValueError:
            flash('Please enter a valid age.', 'danger')
            return redirect(url_for('dashboard'))

        # Update user profile
        current_user.name = name
        current_user.age = age_int
        current_user.education = education
        current_user.interests = interests
        current_user.country = country
        current_user.profile_completed = True

        # Update profile image if new one was uploaded
        if new_image_filename:
            current_user.profile_image = new_image_filename

        db.session.commit()

        flash(
            f'Welcome to CampusConnect, {name}! Your profile has been created successfully.', 'success')
        flash('You can now start connecting with other students who share your interests!', 'info')
        return redirect(url_for('dashboard'))

    # GET request - show profile form if not completed, redirect to dashboard if completed
    if current_user.profile_completed:
        return redirect(url_for('dashboard'))

    # Show dashboard with profile completion modal for new users
    return render_template('dashboard.html',
                           user=current_user,
                           force_profile_modal=True,
                           mutual_matches=[],
                           liked_by=[])


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard - requires authentication"""
    # Redirect to profile if not completed
    if not current_user.profile_completed:
        return redirect(url_for('profile'))

    # Get mutual matches (people who liked each other)
    mutual_matches = db.session.query(User).join(
        Like, Like.liker_id == User.id
    ).filter(
        Like.liked_id == current_user.id,
        Like.liker_id.in_(
            db.session.query(Like.liked_id).filter(
                Like.liker_id == current_user.id)
        )
    ).all()

    # Get IDs of users who are in mutual matches
    mutual_match_user_ids = [user.id for user in mutual_matches]

    # Get people who liked you (but you haven't liked back yet and aren't mutual matches)
    liked_by = User.query.join(Like, Like.liker_id == User.id).filter(
        Like.liked_id == current_user.id,
        ~Like.liker_id.in_(
            db.session.query(Like.liked_id).filter(
                Like.liker_id == current_user.id)
        ),
        ~User.id.in_(mutual_match_user_ids)
    ).all()

    return render_template('dashboard.html', user=current_user,
                           mutual_matches=mutual_matches, liked_by=liked_by)


@app.route('/history')
@login_required
def history():
    """View user's swipe and like history"""
    if not current_user.profile_completed:
        return redirect(url_for('profile'))

    # Get all swipes made by current user
    user_swipes = db.session.query(Swipe, User).join(
        User, Swipe.swiped_id == User.id
    ).filter(
        Swipe.swiper_id == current_user.id
    ).order_by(Swipe.timestamp.desc()).all()

    # Get mutual matches (interactions) - users who liked each other
    mutual_matches = db.session.query(Like, User).join(
        User, Like.liker_id == User.id
    ).filter(
        Like.liked_id == current_user.id,
        Like.liker_id.in_(
            db.session.query(Like.liked_id).filter(
                Like.liker_id == current_user.id)
        )
    ).order_by(Like.timestamp.desc()).all()

    # Get IDs of users who are in mutual matches (to exclude from other tabs)
    mutual_match_user_ids = [match[1].id for match in mutual_matches]

    # Get all likes given by current user (excluding mutual matches)
    user_likes = db.session.query(Like, User).join(
        User, Like.liked_id == User.id
    ).filter(
        Like.liker_id == current_user.id,
        ~Like.liked_id.in_(mutual_match_user_ids)
    ).order_by(Like.timestamp.desc()).all()

    # Get all likes received by current user (excluding mutual matches)
    received_likes = db.session.query(Like, User).join(
        User, Like.liker_id == User.id
    ).filter(
        Like.liked_id == current_user.id,
        ~Like.liker_id.in_(mutual_match_user_ids)
    ).order_by(Like.timestamp.desc()).all()

    # Count statistics
    total_swipes = len(user_swipes)
    likes_given = len(user_likes)
    likes_received = len(received_likes)
    mutual_matches_count = len(mutual_matches)
    swipe_likes = len([s for s in user_swipes if s[0].action == 'like'])
    swipe_declines = len([s for s in user_swipes if s[0].action == 'decline'])

    stats = {
        'total_swipes': total_swipes,
        'likes_given': likes_given,
        'likes_received': likes_received,
        'swipe_likes': swipe_likes,
        'swipe_declines': swipe_declines,
        'mutual_matches': mutual_matches_count
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

    # Initialize session-based seen users list if not exists
    if 'session_seen_users' not in session:
        session['session_seen_users'] = []

    # Get users that have been liked (we don't want to show them again)
    liked_ids = [l.liked_id for l in Like.query.filter_by(
        liker_id=current_user.id)]

    # Get users with mutual connections (both users liked each other)
    mutual_connection_ids = []
    my_likes = Like.query.filter_by(liker_id=current_user.id).all()
    for like in my_likes:
        # Check if they also liked me back
        mutual_like = Like.query.filter_by(
            liker_id=like.liked_id, liked_id=current_user.id).first()
        if mutual_like:
            mutual_connection_ids.append(like.liked_id)

    # Get total available users count for better decision making
    total_available = User.query.filter(
        User.id != current_user.id,
        User.profile_completed == True
    ).count()

    # Adaptive buffer size based on total users available
    if total_available <= 5:
        # Very small user base - minimal restrictions
        recent_buffer_size = 1
        session_buffer_size = 2
        flash('Small user base - showing more variety', 'info')
    elif total_available <= 10:
        # Small user base - reduce restrictions
        recent_buffer_size = 3
        session_buffer_size = 5
    elif total_available <= 20:
        # Medium user base - moderate restrictions
        recent_buffer_size = 8
        session_buffer_size = 8
    else:
        # Large user base - full restrictions
        recent_buffer_size = 20
        session_buffer_size = 10

    # Get users that have been swiped on recently (adaptive buffer size)
    recent_swiped_user_ids = [s.swiped_id for s in Swipe.query.filter_by(
        swiper_id=current_user.id).order_by(Swipe.timestamp.desc()).limit(recent_buffer_size)]

    # Get session seen users (adaptive buffer size)
    session_seen_ids = session['session_seen_users'][-session_buffer_size:
                                                     ] if session['session_seen_users'] else []

    # Always exclude liked users, mutual connections, recently swiped users, and session seen users
    excluded_users = list(set(
        liked_ids + mutual_connection_ids + recent_swiped_user_ids + session_seen_ids + [current_user.id]))

    # Try to find a user not in the excluded list
    user = User.query.filter(
        User.id.notin_(excluded_users),
        User.profile_completed == True
    ).order_by(db.func.random()).first()

    # If no fresh users, try progressively less restrictive approaches
    if not user and total_available > 3:
        # Adaptive fallback based on user base size
        # Use 1/3 of original buffer
        fallback_buffer_size = max(1, recent_buffer_size // 3)

        last_few_swiped_ids = [s.swiped_id for s in Swipe.query.filter_by(
            swiper_id=current_user.id).order_by(Swipe.timestamp.desc()).limit(fallback_buffer_size)]

        excluded_less_strict = list(set(
            liked_ids + mutual_connection_ids + last_few_swiped_ids + [current_user.id]))

        user = User.query.filter(
            User.id.notin_(excluded_less_strict),
            User.profile_completed == True
        ).order_by(db.func.random()).first()

    # If still no user, allow declined users from further back
    if not user:
        # Adaptive offset based on user base size
        # At least 5, or half the buffer size
        decline_offset = max(5, recent_buffer_size // 2)

        # Get users who were declined but not recently
        old_declined_ids = [s.swiped_id for s in Swipe.query.filter_by(
            swiper_id=current_user.id, action='decline'
        ).order_by(Swipe.timestamp.desc()).offset(decline_offset).all()]

        # Only exclude liked users and mutual connections (allow old declined users)
        excluded_for_old = list(
            set(liked_ids + mutual_connection_ids + [current_user.id]))

        user = User.query.filter(
            User.id.in_(old_declined_ids),
            User.id.notin_(excluded_for_old),
            User.profile_completed == True
        ).order_by(db.func.random()).first()

        if user:
            flash('Showing previous profiles again - you might change your mind!', 'info')

    # Final fallback: show anyone except liked/connected users
    if not user:
        excluded_final = list(
            set(liked_ids + mutual_connection_ids + [current_user.id]))

        user = User.query.filter(
            User.id.notin_(excluded_final),
            User.profile_completed == True
        ).order_by(db.func.random()).first()

    # If still no users (only current user exists), show message
    if not user:
        flash('No other students available to explore at the moment!', 'info')
        return redirect(url_for('dashboard'))

    # Add user to session seen list
    if user.id not in session['session_seen_users']:
        session['session_seen_users'].append(user.id)
        # Keep only last 15 seen users to prevent session from growing too large
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

    # Get mutual matches (people who liked each other)
    mutual_matches = db.session.query(User).join(
        Like, Like.liker_id == User.id
    ).filter(
        Like.liked_id == current_user.id,
        Like.liker_id.in_(
            db.session.query(Like.liked_id).filter(
                Like.liker_id == current_user.id)
        )
    ).all()

    return render_template('connections.html',
                           user=current_user,
                           mutual_matches=mutual_matches)


@app.route('/update_contact_info', methods=['POST'])
@login_required
def update_contact_info():
    """Update user's contact information"""
    import re

    # Get form data
    phone_number = request.form.get('whatsapp', '').strip()
    instagram = request.form.get('instagram', '').strip()
    discord = request.form.get('discord', '').strip()
    linkedin = request.form.get('linkedin', '').strip()
    other_contact = request.form.get('other_contact', '').strip()

    # Validate phone number if provided
    if phone_number:
        # Remove common formatting characters
        clean_phone = re.sub(r'[\s\-\(\)\+]', '', phone_number)

        # Check if the cleaned phone number contains only digits
        if not clean_phone.isdigit():
            flash('Phone number must contain only numbers and common formatting characters (+, -, spaces, parentheses).', 'error')
            return redirect(url_for('connections'))

        # Check reasonable length (8-15 digits for international numbers)
        if len(clean_phone) < 8 or len(clean_phone) > 15:
            flash('Phone number must be between 8 and 15 digits long.', 'error')
            return redirect(url_for('connections'))

    # Update user information
    current_user.whatsapp = phone_number
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
# 50 likes per 5 minutes to prevent spam
@require_rate_limit(max_requests=50, window=300)
def like_user(user_id):
    # Input validation
    if not isinstance(user_id, int) or user_id <= 0:
        abort(400)

    # Prevent liking yourself
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
    # Get all users who liked current user
    liked_by = Like.get_liked_by_user(current_user)
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

            # Check for mutual match
            mutual_like = Like.query.filter_by(
                liker_id=user_id, liked_id=current_user.id).first()

            if mutual_like:
                # It's a match! You could add notification logic here
                other_user = User.query.get(user_id)
                db.session.commit()
                return jsonify({'match': True, 'user_name': other_user.name}), 200

        db.session.commit()
        return '', 204

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in swipe: {str(e)}")
        abort(500)
    return '', 204


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
