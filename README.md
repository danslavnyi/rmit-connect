# 🎓 RMIT Connect - Campus Social Network

A modern Flask-based social networking platform designed specifically for RMIT University students to connect, interact, and build meaningful relationships within the campus community.

## ✨ Features

- 🔐 **Passwordless Authentication** - Secure email-based login system
- 👥 **Student Profiles** - Comprehensive profile management with photos
- 💕 **Smart Matching** - Like/match system for meaningful connections
- 📱 **Mobile Responsive** - Optimized for all devices
- 🖼️ **Image Uploads** - Profile photo management with automatic optimization
- ⚡ **Real-time Interactions** - Instant likes, matches, and connections
- 🛡️ **Security First** - Rate limiting, input validation, and secure headers

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL (production) or SQLite (development)
- Modern web browser

### Local Development Setup

1. **Clone the repository:**
```bash
git clone https://github.com/danslavnyi/rmit-connect.git
cd rmit-connect
```

2. **Create and activate virtual environment:**
```bash
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables:**
```bash
# Create .env file with your configuration
echo "SECRET_KEY=your-secret-key-here" > .env
echo "FLASK_ENV=development" >> .env
```

5. **Run the application:**
```bash
python main.py
```

6. **Open your browser:**
Visit `http://localhost:5001` to access RMIT Connect

## 🏗️ Architecture

### Technology Stack

- **Backend:** Flask 3.1.1, SQLAlchemy ORM
- **Database:** PostgreSQL (production), SQLite (development)
- **Frontend:** Bootstrap 5, Vanilla JavaScript
- **Authentication:** Email-based passwordless system
- **Deployment:** Render.com with auto-scaling
- **Security:** Rate limiting, CSRF protection, secure headers

### Project Structure

```
RMIT-Connect/
├── main.py              # Application entry point
├── app.py               # Flask app initialization
├── routes.py            # Application routes and logic
├── models.py            # Database models
├── config.py            # Configuration management
├── security.py          # Security utilities
├── email_templates.py   # Email template functions
├── templates/           # Jinja2 HTML templates
├── static/              # CSS, JS, and uploaded files
├── requirements.txt     # Python dependencies
└── render.yaml          # Deployment configuration
```

## 🚀 Deployment

### Production Deployment on Render

1. **Fork this repository** to your GitHub account

2. **Create a new Web Service** on Render.com:
   - Connect your GitHub repository
   - Set build command: `pip install -r requirements.txt`
   - Set start command: `gunicorn --config gunicorn_config.py main:app`

3. **Create PostgreSQL Database** on Render:
   - Add new PostgreSQL service
   - Copy the external database URL

4. **Set Environment Variables:**
   ```
   DATABASE_URL=postgresql://user:pass@host:port/db
   SECRET_KEY=your-production-secret-key
   FLASK_ENV=production
   BASE_URL=https://your-app.onrender.com
   ```

5. **Deploy** - Render will automatically build and deploy your app

### Health Monitoring

- Health check endpoint: `/health`
- Database status: `/admin/db-status` (temporary)

## 🛡️ Security Features

- **Rate Limiting** - Prevents abuse and spam
- **Input Validation** - Sanitizes all user inputs
- **CSRF Protection** - Secure form submissions
- **Secure Headers** - HSTS, CSP, and security headers
- **Passwordless Auth** - No passwords to steal or forget
- **Image Validation** - Secure file upload handling

## 📊 Performance Optimizations

- **GZIP Compression** - 60-80% smaller responses
- **Static File Caching** - 1-year cache headers
- **Database Connection Pooling** - Optimized PostgreSQL connections
- **Lazy Image Loading** - Faster page loads
- **Deferred JavaScript** - Non-blocking script execution

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Commit: `git commit -m 'Add amazing feature'`
5. Push: `git push origin feature/amazing-feature`
6. Submit a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👥 Support

- **Issues:** Report bugs or request features via GitHub Issues
- **Email:** Contact the development team for support
- **Documentation:** See the wiki for detailed documentation

## 🙏 Acknowledgments

- RMIT University for inspiration
- Flask community for excellent documentation
- Contributors who help improve the platform

---

**Built with ❤️ for the RMIT University community**
