import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def send_otp_email(receiver_email, otp, purpose="registration"):
    """
    Sends a branded verification OTP email via Django's configured Gmail SMTP backend.
    Supports both HTML and plain-text fallbacks.
    """
    subject = "GoOnStay - Your Email Verification Code"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or (f"GoOnStay <{settings.EMAIL_HOST_USER}>" if settings.EMAIL_HOST_USER else 'GoOnStay <noreply@goonstay.com>')

    plain_content = f"""Hello,

Your verification OTP code for GoOnStay is: {otp}

This OTP is valid for 5 minutes. Please do not share this code with anyone.

If you did not request this verification code, please ignore this email.

Best regards,
GoOnStay Team
Book My Room Platform
"""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Email Verification OTP</title>
      <style>
        body {{ margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
        .container {{ max-width: 540px; margin: 30px auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
        .header {{ background: linear-gradient(135deg, #e11d48 0%, #be123c 100%); padding: 28px 24px; text-align: center; color: #ffffff; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
        .header p {{ margin: 6px 0 0; font-size: 12px; opacity: 0.9; }}
        .body {{ padding: 32px 28px; text-align: center; color: #334155; }}
        .otp-box {{ background: #fff1f2; border: 2px dashed #f43f5e; border-radius: 12px; padding: 18px 24px; margin: 24px auto; display: inline-block; }}
        .otp-code {{ font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: 900; letter-spacing: 8px; color: #e11d48; margin: 0; }}
        .footer {{ background: #f8fafc; padding: 20px 24px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 11px; color: #64748b; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>GoOnStay</h1>
          <p>Secure Account Verification</p>
        </div>
        <div class="body">
          <h2 style="margin: 0 0 12px; font-size: 18px; color: #0f172a;">Verify Your Email Address</h2>
          <p style="margin: 0 0 20px; font-size: 14px; line-height: 1.5; color: #475569;">
            Use the 6-digit verification code below to complete your account setup:
          </p>
          <div class="otp-box">
            <div class="otp-code">{otp}</div>
          </div>
          <p style="margin: 16px 0 0; font-size: 12px; font-weight: bold; color: #e11d48;">
            ⏱ This code expires in 5 minutes.
          </p>
          <p style="margin: 12px 0 0; font-size: 12px; color: #94a3b8;">
            If you did not request this verification code, you can safely ignore this email.
          </p>
        </div>
        <div class="footer">
          <p style="margin: 0;">&copy; 2026 GoOnStay • Book My Room. All rights reserved.</p>
          <p style="margin: 4px 0 0;">This is an automated security verification message.</p>
        </div>
      </div>
    </body>
    </html>
    """

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_content,
            from_email=from_email,
            to=[receiver_email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"[OTP Email] Successfully sent OTP verification to {receiver_email}")
        return True
    except Exception as e:
        logger.error(f"[OTP Email Error] Failed to send OTP to {receiver_email}: {e}")
        print(f"[EMAIL SERVICE WARNING] SMTP send failed: {e}")
        return False
