import secrets
import string
import hashlib
import logging
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from .models import StaffProfile, Department, StaffActivityLog, StaffNotification, StaffPasswordResetToken

logger = logging.getLogger(__name__)


def generate_next_employee_id():
    """
    Generates a unique, sequential Employee ID in the format: GOS-EMP-001, GOS-EMP-002, etc.
    """
    last_profile = StaffProfile.objects.order_by('-id').first()
    if not last_profile:
        next_num = 1
    else:
        emp_id = str(last_profile.employee_id or '')
        try:
            parts = emp_id.split('-')
            next_num = int(parts[-1]) + 1
        except Exception:
            next_num = StaffProfile.objects.count() + 1

    candidate = f"GOS-EMP-{next_num:03d}"
    # Collision safeguard
    while StaffProfile.objects.filter(employee_id=candidate).exists():
        next_num += 1
        candidate = f"GOS-EMP-{next_num:03d}"

    return candidate


def generate_login_id(first_name, department_code):
    """
    Generates a unique login identifier in format: <firstname>.<dept_prefix><seq>
    Example: amit.reservation001
    """
    clean_name = ''.join(c for c in (first_name or 'staff').lower() if c.isalnum())
    clean_dept = ''.join(c for c in (department_code or 'general').lower() if c.isalnum())
    
    # Abbreviate department if long
    dept_short = clean_dept.replace('customersupport', 'support').replace('hotelverification', 'verify')
    
    seq = 1
    candidate = f"{clean_name}.{dept_short}{seq:03d}"
    while StaffProfile.objects.filter(login_id=candidate).exists():
        seq += 1
        candidate = f"{clean_name}.{dept_short}{seq:03d}"

    return candidate


def generate_temporary_password(length=12):
    """
    Generates a cryptographically secure temporary password containing
    uppercase, lowercase, digits, and special characters.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one uppercase, lowercase, digit, and special char
        if (any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*" for c in password)):
            return password


def hash_token(raw_token):
    """
    Computes SHA-256 hash of a raw token for safe database persistence.
    """
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def get_client_ip(request):
    """Extracts client IP address safely from request headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_staff_activity(request, staff_profile=None, actor_user=None, action='', entity_type='', entity_id='', description='', metadata=None):
    """
    Records an immutable audit entry in StaffActivityLog.
    Never logs passwords, tokens, or sensitive credentials.
    """
    try:
        ip = get_client_ip(request)
        actor_name = ""
        emp_id = ""

        if actor_user:
            actor_name = actor_user.username
            if hasattr(actor_user, 'staff_profile'):
                emp_id = actor_user.staff_profile.employee_id
            elif str(getattr(actor_user, 'role', '')).upper() in ['ADMIN', 'SUPER_ADMIN']:
                emp_id = "ADMIN"
        elif request and request.user and request.user.is_authenticated:
            actor_name = request.user.username
            if hasattr(request.user, 'staff_profile'):
                emp_id = request.user.staff_profile.employee_id
            elif str(getattr(request.user, 'role', '')).upper() in ['ADMIN', 'SUPER_ADMIN']:
                emp_id = "ADMIN"

        if staff_profile and not emp_id:
            emp_id = staff_profile.employee_id

        # Clean metadata to scrub sensitive keys
        safe_meta = dict(metadata or {})
        for sensitive_key in ['password', 'temp_password', 'token', 'secret', 'key']:
            if sensitive_key in safe_meta:
                safe_meta[sensitive_key] = '[REDACTED]'

        StaffActivityLog.objects.create(
            staff=staff_profile,
            employee_id=emp_id or 'UNKNOWN',
            actor_username=actor_name or 'System',
            action=action,
            target_entity_type=entity_type,
            target_entity_id=str(entity_id),
            description=description,
            metadata=safe_meta,
            ip_address=ip
        )
    except Exception as exc:
        logger.error(f"[log_staff_activity] Error writing audit log: {exc}")


def create_staff_notification(department=None, recipient=None, title='', message='', notification_type='GENERAL', metadata=None):
    """
    Creates a persistent notification for a specific staff member or an entire department.
    """
    try:
        return StaffNotification.objects.create(
            recipient=recipient,
            department=department,
            title=title,
            message=message,
            notification_type=notification_type,
            metadata=metadata or {}
        )
    except Exception as exc:
        logger.error(f"[create_staff_notification] Error creating notification: {exc}")
        return None


def send_staff_password_reset_email(staff_profile, reset_token):
    """
    Sends a secure password reset link to the staff member's registered email address.
    """
    user = staff_profile.user
    if not user.email:
        return False

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'GoOnStay Staff Portal <noreply@goonstay.com>')
    subject = "GoOnStay Staff Portal – Password Reset Request"
    reset_url = f"https://goonstay.com/staff/reset-password?token={reset_token}&emp_id={staff_profile.employee_id}"

    plain_content = f"""Hello {user.first_name or staff_profile.login_id},

A password reset request was initiated for your GoOnStay Staff account ({staff_profile.employee_id}).

Reset Link: {reset_url}

This link is valid for 15 minutes and can only be used once.

If you did not request this password reset, please contact the System Administrator immediately.

GoOnStay Administration Team
"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>Staff Password Reset</title></head>
    <body style="font-family: Arial, sans-serif; background-color: #f8fafc; padding: 20px;">
      <div style="max-width: 520px; margin: auto; background: #fff; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0;">
        <h2 style="color: #0f172a; margin-top: 0;">GoOnStay Staff Portal</h2>
        <p>Hello <strong>{user.first_name or staff_profile.login_id}</strong>,</p>
        <p>A password reset request was received for your staff account (<strong>{staff_profile.employee_id}</strong>).</p>
        <p style="text-align: center; margin: 30px 0;">
          <a href="{reset_url}" style="background-color: #e11d48; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold;">Reset Password</a>
        </p>
        <p style="font-size: 13px; color: #64748b;">This link will expire in 15 minutes and can only be used once.</p>
        <p style="font-size: 12px; color: #94a3b8; border-top: 1px solid #eee; padding-top: 15px;">
          If you did not request this, please notify your Platform Administrator immediately.
        </p>
      </div>
    </body>
    </html>
    """

    try:
        msg = EmailMultiAlternatives(subject, plain_content, from_email, [user.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error(f"[send_staff_password_reset_email] Failed to send email to {user.email}: {exc}")
        return False
