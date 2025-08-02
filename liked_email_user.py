"""
Email templates for RMIT Connect
Centralized email content to avoid duplication
"""


def get_like_notification_email_html(liker, target_user):
    """Get HTML template for like notification email"""
    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0;">RMIT Connect</h1>
                <p style="color: white; margin: 10px 0 0 0;">Your Campus Networking Platform</p>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa;">
                <h2 style="color: #333;">You've received a new like!</h2>
                <p style="color: #666; line-height: 1.6;">
                    Hello {target_user.name or target_user.email},<br>
                    You have received a new like from {liker.name or liker.email}!<br>
                    Log in to your account to see the like and connect with other students.
                </p>
                
                <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
                
                <p style="color: #999; font-size: 14px;">
                    Best regards,<br>
                    The CampusConnect Team
                </p>
            </div>
        </body>
    </html>
    """
