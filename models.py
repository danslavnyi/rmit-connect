from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from security import SecurityUtils
import secrets
import string

# Use the db instance from app
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Security fields
    failed_login_attempts = db.Column(db.Integer, default=0)
    account_locked_until = db.Column(db.DateTime)

    # Profile fields
    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    education = db.Column(db.String(200))
    interests = db.Column(db.Text)
    country = db.Column(db.String(100))
    profile_completed = db.Column(db.Boolean, default=False)
    # Store filename of profile image
    profile_image = db.Column(db.String(255))

    # Contact information (optional, for sharing with mutual matches)
    phone_number = db.Column(db.String(20))
    instagram = db.Column(db.String(50))
    discord = db.Column(db.String(50))
    linkedin = db.Column(db.String(100))
    other_contact = db.Column(db.String(200))

    @staticmethod
    def validate_email(email):
        """Enhanced email validation with security checks"""
        return SecurityUtils.validate_email_security(email)

    def is_account_locked(self):
        """Check if account is temporarily locked"""
        if self.account_locked_until and datetime.utcnow() < self.account_locked_until:
            return True
        return False

    def record_failed_login(self):
        """Record failed login attempt and lock account if needed"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            # Lock account for 1 hour after 5 failed attempts
            self.account_locked_until = datetime.utcnow() + timedelta(hours=1)

    def record_successful_login(self):
        """Reset failed login attempts on successful login"""
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.last_login = datetime.utcnow()

    def get_profile_image_url(self):
        """Get the URL for the user's profile image with fallback"""
        if self.profile_image and self.profile_image.strip():
            # Validate that the profile image filename is not empty or just whitespace
            return f"/uploads/{self.profile_image}"
        return "/static/images/default-profile.png"

    def is_profile_complete(self):
        """Check if user has completed their profile with all required information"""
        return (
            self.profile_completed and
            self.name and
            self.age and
            self.education and
            self.country
        )

    def is_new_user(self):
        """Check if user is new (has incomplete profile)"""
        return not self.is_profile_complete()

    def __repr__(self):
        return f'<User {self.email}>'


class PermanentLoginLink(db.Model):
    __tablename__ = 'permanent_login_links'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref=db.backref(
        'permanent_links', lazy=True))

    @staticmethod
    def generate_token():
        """Generate a secure random token"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))

    @staticmethod
    def create_or_get_link(user_id):
        """Create a new permanent link or get existing active one for a user"""
        # Check if user already has an active permanent link
        existing_link = PermanentLoginLink.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if existing_link:
            return existing_link

        # Create new permanent link
        token = PermanentLoginLink.generate_token()
        permanent_link = PermanentLoginLink(
            token=token,
            user_id=user_id
        )

        db.session.add(permanent_link)
        db.session.commit()

        return permanent_link

    def is_valid(self):
        """Check if link is still valid"""
        return self.is_active

    def use_link(self):
        """Update last used timestamp"""
        self.last_used = datetime.utcnow()
        db.session.commit()

    def deactivate(self):
        """Deactivate the link"""
        self.is_active = False
        db.session.commit()

    def __repr__(self):
        return f'<PermanentLoginLink {self.token[:8]}... for {self.user.email}>'


class Like(db.Model):
    __tablename__ = 'likes'

    id = db.Column(db.Integer, primary_key=True)
    liker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    liked_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

    liker = db.relationship('User', foreign_keys=[liker_id])
    liked = db.relationship('User', foreign_keys=[liked_id])

    def __repr__(self):
        return f'<Like {self.liker.email} -> {self.liked.email}>'

    @staticmethod
    def get_liked_by_user(current_user):
        """Get users who liked the current user"""
        liked_by = User.query.join(Like, Like.liker_id == User.id).filter(
            Like.liked_id == current_user.id).all()
        return liked_by


class Swipe(db.Model):
    __tablename__ = 'swipes'
    id = db.Column(db.Integer, primary_key=True)
    swiper_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False)
    swiped_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(10), nullable=False)  # 'like' or 'decline'
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
