"""
Email templates for RMIT Connect
Centralized email content to avoid duplication
"""


def get_login_email_html(login_url):
    """Get HTML template for login email"""
    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0;">RMIT Connect</h1>
                <p style="color: white; margin: 10px 0 0 0;">Your Campus Networking Platform</p>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa;">
                <h2 style="color: #333;">Welcome to RMIT Connect!</h2>
                <p style="color: #666; line-height: 1.6;">
                    Click the button below to securely log into your account:
                </p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{login_url}" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; 
                              padding: 15px 30px; 
                              text-decoration: none; 
                              border-radius: 25px; 
                              font-weight: bold;
                              display: inline-block;">
                        🚀 Login to RMIT Connect
                    </a>
                </div>
                
                <p style="color: #666; line-height: 1.6;">
                    Or copy and paste this link into your browser:
                </p>
                <p style="background-color: #e9ecef; padding: 10px; border-radius: 5px; word-break: break-all; font-family: monospace;">
                    {login_url}
                </p>
                
                <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
                
                <p style="color: #999; font-size: 14px;">
                    This login link is permanent and secure. Keep it safe! <br>
                    If you didn't request this, please ignore this email.
                </p>
            </div>
        </body>
    </html>
    """
