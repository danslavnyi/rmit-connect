from app import app, db, mail
from models import User, PermanentLoginLink, Like, Swipe
from email_templates import get_login_email_html
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, abort, jsonify, send_from_directory, make_response
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, exists
from sqlalchemy.orm import aliased
from security import require_rate_limit, SecurityUtils
from flask_mail import Message
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import uuid
import re
import time

# Upload settings
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def get_optimized_image_url(filename, size='medium'):
    """
    Get URL for optimized image with fallback support.

    Args:
        filename: Original filename
        size: 'thumbnail', 'medium', or 'large'

    Returns:
        URL for the optimized image
    """
    # Always provide a fallback image if filename is missing or file does not exist
    uploads_folder = app.config.get('UPLOAD_FOLDER', os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
    default_image = 'default.webp'
    if not filename:
        filename = default_image
    # Check if file exists
    if size == 'large':
        file_path = os.path.join(uploads_folder, filename)
        if not os.path.exists(file_path):
            filename = default_image
        try:
            return url_for('uploaded_file', filename=filename)
        except RuntimeError:
            return f"/uploads/{filename}"
    else:
        base_name = filename.rsplit('.', 1)[0]
        sized_filename = f"{base_name}_{size}.webp"
        file_path = os.path.join(uploads_folder, sized_filename)
        if not os.path.exists(file_path):
            sized_filename = default_image
        try:
            return url_for('uploaded_file', filename=sized_filename)
        except RuntimeError:
            return f"/uploads/{sized_filename}"

    try:
        if size == 'large':
            return url_for('uploaded_file', filename=filename)
        else:
            base_name = filename.rsplit('.', 1)[0]
            sized_filename = f"{base_name}_{size}.webp"
            return url_for('uploaded_file', filename=sized_filename)
    except RuntimeError:
        # Fallback if not in request context
        if size == 'large':
            return f"/uploads/{filename}"
        else:
            base_name = filename.rsplit('.', 1)[0]
            sized_filename = f"{base_name}_{size}.webp"
            return f"/uploads/{sized_filename}"


@app.context_processor
def inject_image_helpers():
    """Make image optimization functions available in templates"""
    return {
        'get_optimized_image_url': get_optimized_image_url,
        'image_sizes': ['thumbnail', 'medium', 'large']
    }


def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
# Standalone image processing function for uploads


def process_image(image_file, user_id):
    """
    Process and optimize uploaded profile image for a user.
    Returns (filename, message) or (None, error_message)
    """
    if not image_file or not allowed_file(image_file.filename):
        return None, "Invalid file type. Please upload PNG, JPG, JPEG, GIF, or WebP images."

    try:
        # Create unique filename (always save as WebP for best compression)
        unique_filename = f"user_{user_id}_{uuid.uuid4().hex[:8]}.webp"

        # Process image directly from memory (no temp file needed)
        img = Image.open(image_file)

        # Strip EXIF data for privacy and smaller file size
        img_data = list(img.getdata())
        img_clean = Image.new(img.mode, img.size)
        img_clean.putdata(img_data)

        # Convert to RGB for better compression (WebP works best with RGB)
        if img_clean.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparent images
            background = Image.new('RGB', img_clean.size, (255, 255, 255))
            if img_clean.mode == 'RGBA':
                background.paste(img_clean, mask=img_clean.split()[-1])
            else:
                background.paste(img_clean)
            img_clean = background
        elif img_clean.mode != 'RGB':
            img_clean = img_clean.convert('RGB')

        # Smart resizing with quality preservation
        # Multiple sizes for different use cases
        sizes = {
            'thumbnail': (150, 150),    # Profile thumbnails
            'medium': (400, 400),       # Profile cards
            'large': (800, 800)         # Full profile view
        }

        saved_files = []

        for size_name, max_size in sizes.items():
            # Create copy for each size
            img_resized = img_clean.copy()

            # Smart resize: maintain aspect ratio and crop to square if needed
            width, height = img_resized.size

            # Make square by cropping to center
            min_dimension = min(width, height)
            left = (width - min_dimension) // 2
            top = (height - min_dimension) // 2
            right = left + min_dimension
            bottom = top + min_dimension

            img_square = img_resized.crop((left, top, right, bottom))

            # Resize to target size with high-quality resampling
            img_final = img_square.resize(max_size, Image.Resampling.LANCZOS)

            # Apply smart sharpening for small images
            if max_size[0] <= 400:
                from PIL import ImageFilter
                img_final = img_final.filter(ImageFilter.UnsharpMask(
                    radius=1.0, percent=120, threshold=1))

            # Generate filename for this size
            if size_name == 'large':
                size_filename = unique_filename  # Main file
            else:
                base_name = unique_filename.rsplit('.', 1)[0]
                size_filename = f"{base_name}_{size_name}.webp"

            final_path = os.path.join(
                app.config['UPLOAD_FOLDER'], size_filename)

            # Save with optimal WebP settings
            img_final.save(
                final_path,
                'WebP',
                optimize=True,
                quality=82 if size_name == 'large' else 75,  # Higher quality for larger images
                method=6,  # Best compression method
                lossless=False,
                exact=False
            )

            saved_files.append(size_filename)

        # Also create a fallback JPEG for older browsers
        jpeg_filename = unique_filename.replace('.webp', '.jpg')
        jpeg_path = os.path.join(app.config['UPLOAD_FOLDER'], jpeg_filename)

        # Resize for JPEG (use medium size)
        img_jpeg = img_clean.copy()
        width, height = img_jpeg.size
        min_dimension = min(width, height)
        left = (width - min_dimension) // 2
        top = (height - min_dimension) // 2
        img_square = img_jpeg.crop(
            (left, top, left + min_dimension, top + min_dimension))
        img_jpeg_final = img_square.resize(
            (400, 400), Image.Resampling.LANCZOS)

        img_jpeg_final.save(
            jpeg_path,
            'JPEG',
            optimize=True,
            quality=78,
            progressive=True,  # Progressive JPEG for faster perceived loading
            subsampling=2,     # Better compression
            qtables='web_high'  # Web-optimized quality tables
        )

        # Return the main WebP filename (large size)
        return unique_filename, f"Image optimized successfully! Generated {len(saved_files) + 1} variants."

    except Exception as e:
        app.logger.error(
            f"Image processing error for user {user_id}: {str(e)}")
        return None, f"Error processing image: Please try a different image."


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files securely with optimized delivery"""
    try:
        uploads_folder = app.config.get('UPLOAD_FOLDER', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
        default_image = 'default.webp'
        file_path = os.path.join(uploads_folder, filename)
        if not os.path.exists(file_path):
            # Fallback to default image if requested file does not exist
            app.logger.warning(
                f"Requested image '{filename}' not found, serving default image.")
            filename = default_image
            file_path = os.path.join(uploads_folder, filename)
            if not os.path.exists(file_path):
                app.logger.error(
                    f"Default image '{default_image}' not found in uploads folder.")
                abort(404)

        response = send_from_directory(
            uploads_folder,
            filename,
            conditional=True
        )
        response.cache_control.max_age = 31536000
        response.cache_control.public = True
        if filename.endswith('.webp'):
            response.headers['Content-Type'] = 'image/webp'
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

        # Handle dynamic contact fields
        contact_type = request.form.get('contact_type', '').strip()
        contact_value = request.form.get('contact_value', '').strip()

        # Legacy phone number field (for backward compatibility)
        phone_number = request.form.get('phone_number', '').strip()

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

        # Check if contact info is provided (either new dynamic contact or legacy phone)
        if not contact_value and not phone_number:
            missing_fields.append(
                'Contact Information (Phone Number or Instagram)')

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

        # Validate contact information
        if contact_value and contact_type:
            if contact_type == 'phone':
                # Validate phone number
                clean_phone = re.sub(r'[\s\-\(\)\+]', '', contact_value)
                if not clean_phone.isdigit():
                    flash(
                        'Phone number must contain only numbers and common formatting characters (+, -, spaces, parentheses).', 'danger')
                    return redirect(url_for('dashboard'))
                if not (8 <= len(clean_phone) <= 15):
                    flash(
                        'Phone number must be between 8 and 15 digits long.', 'danger')
                    return redirect(url_for('dashboard'))
            elif contact_type == 'instagram':
                # Validate Instagram username (alphanumeric, underscores, periods)
                if not re.match(r'^[a-zA-Z0-9._]+$', contact_value):
                    flash(
                        'Instagram username can only contain letters, numbers, underscores, and periods.', 'danger')
                    return redirect(url_for('dashboard'))
                if len(contact_value) > 30:
                    flash(
                        'Instagram username cannot be longer than 30 characters.', 'danger')
                    return redirect(url_for('dashboard'))

        # Legacy phone number validation (for backward compatibility)
        if phone_number:
            clean_phone = re.sub(r'[\s\-\(\)\+]', '', phone_number)
            if not clean_phone.isdigit():
                flash(
                    'Phone number must contain only numbers and common formatting characters (+, -, spaces, parentheses).', 'danger')
                return redirect(url_for('dashboard'))
            if not (8 <= len(clean_phone) <= 15):
                flash('Phone number must be between 8 and 15 digits long.', 'danger')
                return redirect(url_for('dashboard'))

        # Update user profile
        current_user.name = name
        current_user.age = age_int
        current_user.education = education
        current_user.interests = interests
        current_user.country = country

        # Handle contact information storage
        if contact_value and contact_type:
            if contact_type == 'phone':
                current_user.phone_number = contact_value
                current_user.instagram = None  # Clear other contact method
            elif contact_type == 'instagram':
                current_user.instagram = contact_value
                current_user.phone_number = None  # Clear other contact method
        elif phone_number:
            # Legacy phone number handling
            current_user.phone_number = phone_number

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
    if not current_user.profile_completed:
        return redirect(url_for('profile'))

    # Get mutual matches and liked by users using optimized functions
    mutual_matches = get_mutual_matches(current_user.id)
    liked_by = get_liked_by_users(current_user.id)

    return render_template('dashboard.html',
                           user=current_user,
                           mutual_matches=mutual_matches,
                           liked_by=liked_by)


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


# Performance and SEO routes
@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    start_time = time.time()
    try:
        # Test database connection
        db.session.execute('SELECT 1')
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


@app.route('/admin/db-status')
def admin_db_status():
    """Check database connection and show info - REMOVE AFTER TESTING"""
    try:
        # Test database connection
        result = db.session.execute('SELECT version()').fetchone()
        db_version = result[0] if result else 'Unknown'

        # Get database URL (hide password)
        db_url = os.environ.get('DATABASE_URL', 'Not set')
        safe_db_url = db_url.replace(db_url.split(':')[2].split(
            '@')[0], '****') if '@' in db_url else db_url

        # Test table creation
        db.create_all()

        # Count existing tables
        tables_query = """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public'
        """
        tables_result = db.session.execute(tables_query).fetchall()
        table_names = [row[0] for row in tables_result]

        return jsonify({
            'status': 'Connected to PostgreSQL',
            'database_url': safe_db_url,
            'version': db_version,
            'tables_created': table_names,
            'environment': os.environ.get('FLASK_ENV', 'production'),
            'total_tables': len(table_names)
        })

    except Exception as e:
        return jsonify({
            'status': 'Database connection failed',
            'error': str(e),
            'database_url': 'Check environment variable'
        }), 500


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
