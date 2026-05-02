"""
Django settings for voting_system project.
NHEA Voting Platform — Production-ready configuration.

All secrets are read from environment variables (never hardcoded).
Local dev:   put values in a .env file at the project root (same folder as manage.py).
Production:  set them in Vercel → Project Settings → Environment Variables.
"""

from pathlib import Path
import os
import dj_database_url
from decouple import config, Csv
import cloudinary
import cloudinary.uploader
import cloudinary.api


# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# CORE SECURITY
# ─────────────────────────────────────────────────────────────────────────────

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost',
    cast=Csv()
)

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://127.0.0.1,http://localhost',
    cast=Csv(),
)


# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    # Django built-ins
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Project app
    'voting.apps.VotingConfig',

    # Third-party
    'widget_tweaks',
    'cloudinary',
    'cloudinary_storage',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # ← must be 2nd, before everything else
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'voting_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'voting_system.wsgi.application'


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE  (Neon.tech PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────

DATABASES = {
    'default': dj_database_url.parse(
        config('DATABASE_URL'),
        conn_max_age=600,
        ssl_require=True,
    )
}


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = 'voting.Voter'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL          = 'login'
LOGIN_REDIRECT_URL = 'voting_dashboard'


# ─────────────────────────────────────────────────────────────────────────────
# CLOUDINARY  (image / media storage for nominee photos)
# ─────────────────────────────────────────────────────────────────────────────

cloudinary.config(
    cloud_name = config('CLOUDINARY_CLOUD_NAME'),
    api_key    = config('CLOUDINARY_API_KEY'),
    api_secret = config('CLOUDINARY_API_SECRET'),
    secure     = True,
)

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': config('CLOUDINARY_CLOUD_NAME'),
    'API_KEY':    config('CLOUDINARY_API_KEY'),
    'API_SECRET': config('CLOUDINARY_API_SECRET'),
}


# ─────────────────────────────────────────────────────────────────────────────
# BREVO  (transactional email — Email OTP)
# ─────────────────────────────────────────────────────────────────────────────

BREVO_API_KEY      = config('BREVO_API_KEY')
BREVO_SENDER_EMAIL = config('BREVO_SENDER_EMAIL')
BREVO_SENDER_NAME  = config('BREVO_SENDER_NAME', default='NHEA Voting')


# ─────────────────────────────────────────────────────────────────────────────
# FIREBASE  (phone OTP — server-side token verification)
# ─────────────────────────────────────────────────────────────────────────────

FIREBASE_WEB_API_KEY          = config('FIREBASE_WEB_API_KEY', default='')
FIREBASE_SERVICE_ACCOUNT_JSON = config('FIREBASE_SERVICE_ACCOUNT_JSON', default='')

# Initialise Firebase Admin SDK once at startup (only if credentials are provided)
if FIREBASE_SERVICE_ACCOUNT_JSON:
    import firebase_admin
    from firebase_admin import credentials as fb_credentials
    if not firebase_admin._apps:
        _fb_cred = fb_credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_JSON)
        firebase_admin.initialize_app(_fb_cred)


# ─────────────────────────────────────────────────────────────────────────────
# CACHE  (OTP storage + geo IP caching)
# Redis is recommended for production. Falls back to local memory in dev.
# ─────────────────────────────────────────────────────────────────────────────

REDIS_URL = config('REDIS_URL', default='')

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'TIMEOUT': 300,
        }
    }
else:
    # Fine for local dev and single-worker deploys.
    # OTPs work but won't survive a server restart.
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'nhea-cache',
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

SESSION_ENGINE          = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE      = 60 * 60 * 8   # 8 hours
SESSION_COOKIE_NAME     = 'nhea_session'
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = False


# ─────────────────────────────────────────────────────────────────────────────
# HTTPS / PRODUCTION SECURITY  (auto-enabled when DEBUG=False)
# ─────────────────────────────────────────────────────────────────────────────

if not DEBUG:
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_SSL_REDIRECT            = True
    SECURE_HSTS_SECONDS            = 31536000   # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD            = True
    SECURE_BROWSER_XSS_FILTER      = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    X_FRAME_OPTIONS                = 'DENY'


# ─────────────────────────────────────────────────────────────────────────────
# INTERNATIONALISATION
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Africa/Lagos'
USE_I18N      = True
USE_TZ        = True


# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILES  (WhiteNoise serves on Vercel — no separate CDN needed)
# ─────────────────────────────────────────────────────────────────────────────

STATIC_URL       = '/static/'
STATIC_ROOT      = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# ─────────────────────────────────────────────────────────────────────────────
# MEDIA FILES  (Cloudinary handles uploads; MEDIA_ROOT is local-dev only)
# ─────────────────────────────────────────────────────────────────────────────

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING  (console output; Vercel captures stdout automatically)
# ─────────────────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'voting': {   # covers geo_utils, otp_utils, log_utils
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MISC
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Protects admin-only actions like "Reset all votes"
ELECTION_ACCESS_CODE = config('ELECTION_ACCESS_CODE', default='changeme123')