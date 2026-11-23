import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(os.path.join(BASE_DIR, '.env'))

# Environment Detection
ENVIRONMENT = os.getenv('DJANGO_ENV', os.getenv('ENVIRONMENT', 'development')).lower().strip()
IS_PRODUCTION = ENVIRONMENT in ('production', 'prod')

# Insecure placeholder keys that must NEVER be used in production
INSECURE_PLACEHOLDER_KEYS = {
    'django-insecure-bookmyroom-super-secret-key-production-2026',
    'django-insecure-default-key-change-in-production',
    'changeme',
    'secret',
}

# DEBUG configuration
DEBUG_ENV = os.getenv('DEBUG')
if DEBUG_ENV is not None:
    DEBUG = DEBUG_ENV.lower() in ('true', '1', 'yes')
else:
    DEBUG = not IS_PRODUCTION

# Security Guard: Production must never start with DEBUG=True
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured(
        "Security Violation: DEBUG cannot be set to True in a production environment."
    )

# SECRET_KEY configuration
RAW_SECRET_KEY = os.getenv('SECRET_KEY')
if IS_PRODUCTION or not DEBUG:
    if not RAW_SECRET_KEY:
        raise ImproperlyConfigured(
            "Production Configuration Error: The SECRET_KEY environment variable is missing. "
            "A strong, unique SECRET_KEY must be provided in production."
        )
    if RAW_SECRET_KEY in INSECURE_PLACEHOLDER_KEYS or 'insecure' in RAW_SECRET_KEY.lower():
        raise ImproperlyConfigured(
            "Production Configuration Error: An insecure or well-known placeholder SECRET_KEY "
            "is configured. Please generate and set a cryptographically secure SECRET_KEY in your environment."
        )
    SECRET_KEY = RAW_SECRET_KEY
else:
    # Development workstation fallback
    SECRET_KEY = RAW_SECRET_KEY or 'django-insecure-bookmyroom-local-dev-fallback-key'

# ALLOWED_HOSTS configuration
raw_allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
if DEBUG:
    ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(',') if h.strip()] if raw_allowed_hosts else ['*']
else:
    if not raw_allowed_hosts or raw_allowed_hosts.strip() in ('*', ''):
        raise ImproperlyConfigured(
            "Production Configuration Error: ALLOWED_HOSTS cannot be empty or wildcard ('*') when DEBUG is False. "
            "Specify comma-separated valid domain names or IP addresses (e.g. 'goonstay.com,api.goonstay.com')."
        )
    ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(',') if h.strip() and h.strip() != '*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party packages
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    # Internal Apps
    'users',
    'hotels',
    'rooms',
    'bookings',
    'payments',
    'reviews',
    'wishlist',
    'coupons',
    'notifications',
    'staff',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'core.middleware.RequestCorrelationMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database Setup: Supports PostgreSQL or SQLite fallback
USE_POSTGRES = os.getenv('USE_POSTGRES', 'False').lower() in ('true', '1', 'yes')

if USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'bookmyroom_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 60,
            },
        }
    }

# Ensure SQLite connections use 60s timeout and NORMAL synchronous mode for high concurrent read/write stability
from django.db.backends.signals import connection_created
def _configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        try:
            cursor = connection.cursor()
            cursor.execute('PRAGMA busy_timeout = 60000;')
            cursor.execute('PRAGMA synchronous = NORMAL;')
        except Exception:
            pass
connection_created.connect(_configure_sqlite_connection)

# Caching Configuration (P3-FINDING-07)
REDIS_URL = os.getenv('REDIS_URL', '')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'goonstay-locmem-cache',
            'TIMEOUT': 300,
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.authentication.FlexibleJWTAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    # Standardized API Error Responses (TASK-18 / RFC 7807)
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    # Rate Limiting & Throttling (TASK-19)
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute',
        'user': '1000/minute',
        'login': '5/minute',
        'register': '5/minute',
        'otp_verify': '5/minute',
        'password_reset': '5/minute',
        'check_phone': '15/minute',
        'check_email': '15/minute',
        'email_resend': '5/minute',
        'support_ticket_create': '10/hour',
        'support_ticket_message': '30/hour',
        'booking_create': '15/minute',
        'order_create': '15/minute',
        'coupon_apply': '20/minute',
    }
}

# SimpleJWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# CORS Configuration (TASK-19)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    r"^https?://(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+)(:\d+)?$",
]
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Security Headers & Deployment Hardening (TASK-19 / P3-FINDING-06)
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() in ('true', '1', 'yes')
    CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', 'True').lower() in ('true', '1', 'yes')
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True').lower() in ('true', '1', 'yes')
    SECURE_HSTS_PRELOAD = os.getenv('SECURE_HSTS_PRELOAD', 'True').lower() in ('true', '1', 'yes')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_BROWSER_XSS_FILTER = True
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_BROWSER_XSS_FILTER = True

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media Files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email Configuration (Gmail SMTP)
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER') or os.getenv('MAIL_USERNAME', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD') or os.getenv('MAIL_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL') or (f"Book My Room <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else 'Book My Room <noreply@bookmyroom.com>')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', 15))

# Razorpay Configuration
PAYMENT_MODE = os.getenv('PAYMENT_MODE', 'test').lower().strip()
IS_LIVE_PAYMENT = PAYMENT_MODE in ('live', 'production')

RAW_RZP_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAW_RZP_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
RAW_RZP_WEBHOOK_SECRET = os.getenv('RAZORPAY_WEBHOOK_SECRET')

INSECURE_TEST_KEYS = {
    'rzp_test_bookmyroom_key_2026',
    'rzp_test_bookmyroom_secret_2026',
    'rzp_whsec_bookmyroom_2026'
}

if IS_LIVE_PAYMENT:
    if not RAW_RZP_KEY_ID or RAW_RZP_KEY_ID in INSECURE_TEST_KEYS:
        raise ImproperlyConfigured(
            "Production Payment Gateway Error: Live PAYMENT_MODE requires a valid production RAZORPAY_KEY_ID."
        )
    if not RAW_RZP_KEY_SECRET or RAW_RZP_KEY_SECRET in INSECURE_TEST_KEYS:
        raise ImproperlyConfigured(
            "Production Payment Gateway Error: Live PAYMENT_MODE requires a valid production RAZORPAY_KEY_SECRET."
        )
    if not RAW_RZP_WEBHOOK_SECRET or RAW_RZP_WEBHOOK_SECRET in INSECURE_TEST_KEYS:
        raise ImproperlyConfigured(
            "Production Payment Gateway Error: Live PAYMENT_MODE requires a valid production RAZORPAY_WEBHOOK_SECRET."
        )
    RAZORPAY_KEY_ID = RAW_RZP_KEY_ID
    RAZORPAY_KEY_SECRET = RAW_RZP_KEY_SECRET
    RAZORPAY_WEBHOOK_SECRET = RAW_RZP_WEBHOOK_SECRET
else:
    # Test / Development mode fallback
    RAZORPAY_KEY_ID = RAW_RZP_KEY_ID or 'rzp_test_bookmyroom_key_2026'
    RAZORPAY_KEY_SECRET = RAW_RZP_KEY_SECRET or 'rzp_test_bookmyroom_secret_2026'
    RAZORPAY_WEBHOOK_SECRET = RAW_RZP_WEBHOOK_SECRET or 'rzp_whsec_bookmyroom_2026'

# Payment Hold Configuration (Immediate unlock & fallback duration)
PAYMENT_HOLD_DURATION_MINUTES = int(os.getenv('PAYMENT_HOLD_DURATION_MINUTES', 15))

# Cloudinary Direct Upload Configuration
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', 'bzb1bndw')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY', '894358896518227')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET', '')
CLOUDINARY_URL = os.getenv('CLOUDINARY_URL', '')

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    try:
        import cloudinary
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True
        )
    except Exception:
        pass

# Production Structured Logging & Error Tracking (P3-FINDING-04)
import logging
import logging.handlers

LOGS_DIR = BASE_DIR / 'logs'
try:
    LOGS_DIR.mkdir(exist_ok=True)
except Exception:
    pass

class SensitiveDataLogFilter(logging.Filter):
    """
    Sanitizes sensitive keywords (passwords, tokens, secrets) from log messages
    to prevent accidental credential leakage in log streams.
    """
    SENSITIVE_PATTERNS = ('password', 'secret', 'token', 'authorization', 'bearer', 'cvv', 'card')

    def filter(self, record):
        if isinstance(record.msg, str):
            msg_lower = record.msg.lower()
            if any(p in msg_lower for p in self.SENSITIVE_PATTERNS):
                import re
                record.msg = re.sub(
                    r'(?i)(password|secret|token|key|authorization|bearer)\s*[:=]\s*[\'\"]?([^\s,\'\"]+)',
                    r'\1=********',
                    record.msg
                )
        return True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'sensitive_data_filter': {
            '()': SensitiveDataLogFilter,
        },
    },
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] [{name}] {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['sensitive_data_filter'],
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'goonstay.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['sensitive_data_filter'],
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'core': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'bookings': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'payments': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'hotels': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'rooms': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'staff': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'users': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
    },
}

