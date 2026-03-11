"""
DjangoPress default settings.

Child sites import with:
    from djangopress.settings import *

Then override BASE_DIR, SECRET_KEY, DATABASES, ROOT_URLCONF,
WSGI_APPLICATION, STATIC_ROOT, MEDIA_ROOT, etc.
"""
import warnings
from pathlib import Path

import environ

from django.utils.translation import gettext_lazy as _

# Package root directory (where this settings.py lives)
_PACKAGE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Environment — auto-load .env from working directory if present
# ---------------------------------------------------------------------------
env = environ.Env()

# Try to load .env from CWD (where manage.py lives) so that all env vars
# are available before any settings are evaluated. Child sites no longer
# need to worry about import order.
_dotenv_path = Path.cwd() / '.env'
if _dotenv_path.is_file():
    env.read_env(str(_dotenv_path))

ENVIRONMENT = env('ENVIRONMENT', default='development')
DEBUG_MODE = env.bool('DEBUG_MODE', default=False)

# Enable DEBUG if in development OR if DEBUG_MODE is explicitly enabled
DEBUG = ENVIRONMENT == 'development' or DEBUG_MODE

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.railway.app']

# Site Configuration
SITE_NAME = "DjangoPress"


# ---------------------------------------------------------------------------
# Installed apps
# ---------------------------------------------------------------------------
DJANGOPRESS_APPS = [
    'djangopress.ai',
    'djangopress.backoffice',
    'djangopress.editor_v2',
    'djangopress.core',
    'djangopress.news',
    'djangopress.site_assistant',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'anymail',
    'storages',
] + DJANGOPRESS_APPS

# Add whitenoise.runserver_nostatic only in production
if ENVIRONMENT != 'development':
    INSTALLED_APPS.insert(0, 'whitenoise.runserver_nostatic')


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'djangopress.core.middleware.LocaleMiddleware',
    'djangopress.core.middleware.DynamicLanguageMiddleware',
    'django.middleware.common.CommonMiddleware',
    'djangopress.core.rate_limit.RateLimitMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'djangopress.core.middleware.DomainMiddleware',
    'djangopress.core.middleware.MaintenanceModeMiddleware',
]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [_PACKAGE_DIR / 'templates'],  # Package root templates (base.html, error pages)
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'djangopress.core.context_processors.site_settings',
            ],
            'debug': DEBUG,
        },
    },
]


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('pt', 'Portuguese')]
# LOCALE_PATHS is not set here — child site adds its own locale dir
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [_PACKAGE_DIR / 'static']  # Package-level static files (lightbox, etc.)

# STATICFILES_STORAGE depending on environment
if ENVIRONMENT == 'development':
    STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage'
    warnings.warn("Running in DEVELOPMENT mode. collectstatic is NOT required.")
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

_staticfiles_backend = (
    "whitenoise.storage.StaticFilesStorage" if ENVIRONMENT == 'development'
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)


# ---------------------------------------------------------------------------
# Media files — GCS if configured, local filesystem otherwise
# ---------------------------------------------------------------------------
GS_BUCKET_NAME = env('GS_BUCKET_NAME', default='')

if GS_BUCKET_NAME:
    import json
    from google.oauth2 import service_account

    GS_PROJECT_ID = env('GS_PROJECT_ID', default='')

    MEDIA_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/'

    # Credentials setup — supports both JSON string and file path
    _credentials_json = env('GCS_CREDENTIALS_JSON', default='')
    _credentials_path = env('GS_CREDENTIALS_FILE_PATH', default='')

    if _credentials_json:
        GS_CREDENTIALS = service_account.Credentials.from_service_account_info(
            json.loads(_credentials_json)
        )
    elif _credentials_path:
        GS_CREDENTIALS = service_account.Credentials.from_service_account_file(
            _credentials_path
        )
    else:
        GS_CREDENTIALS = None

    GS_DEFAULT_ACL = None
    GS_FILE_OVERWRITE = False
    GS_MAX_MEMORY_SIZE = 5242880  # 5 MB
    GS_QUERYSTRING_AUTH = False

    STORAGES = {
        "default": {
            "BACKEND": "djangopress.storage_backends.DomainBasedStorage",
        },
        "staticfiles": {
            "BACKEND": _staticfiles_backend,
        },
    }
    DEFAULT_FILE_STORAGE = 'djangopress.storage_backends.DomainBasedStorage'
else:
    MEDIA_URL = '/media/'
    # MEDIA_ROOT — child site defines this based on BASE_DIR

    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": _staticfiles_backend,
        },
    }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_SAVE_EVERY_REQUEST = True  # Sliding window


# ---------------------------------------------------------------------------
# Security — production-only
# ---------------------------------------------------------------------------
if ENVIRONMENT != 'development':
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = False
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = [
    'http://localhost',
    'http://127.0.0.1',
    'https://*.railway.app',
    'https://*.up.railway.app',
]


# ---------------------------------------------------------------------------
# Authentication URLs
# ---------------------------------------------------------------------------
LOGIN_URL = '/backoffice/login/'
LOGIN_REDIRECT_URL = '/backoffice/'
LOGOUT_REDIRECT_URL = '/backoffice/login/'


# ---------------------------------------------------------------------------
# Email — Mailgun in production, console in development
# ---------------------------------------------------------------------------
if ENVIRONMENT == 'development':
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
    ANYMAIL = {
        "MAILGUN_API_KEY": env('MAILGUN_API_KEY', default=''),
        "MAILGUN_API_URL": env('MAILGUN_API_URL', default='https://api.eu.mailgun.net/v3'),
    }

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@sendermail.io')
SERVER_EMAIL = DEFAULT_FROM_EMAIL


# ---------------------------------------------------------------------------
# AI provider API keys
# ---------------------------------------------------------------------------
GEMINI_API_KEY = env('GEMINI_API_KEY', default='')
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY', default='')
UNSPLASH_ACCESS_KEY = env('UNSPLASH_ACCESS_KEY', default='')

# Refinement agent: True = use agentic router (gemini-flash picks model/context)
USE_REFINEMENT_AGENT = env.bool('USE_REFINEMENT_AGENT', default=True)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
ENABLE_DEBUG_LOGGING = env.bool('ENABLE_DEBUG_LOGGING', default=False)

if DEBUG_MODE or ENABLE_DEBUG_LOGGING or ENVIRONMENT != 'development':
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': True,
            },
            'django.template': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False,
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    }
else:
    # Always show template errors even without debug logging
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'django.template': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
        },
    }


# ---------------------------------------------------------------------------
# DjangoPress version
# ---------------------------------------------------------------------------
from djangopress import __version__ as DJANGOPRESS_VERSION  # noqa: E402
