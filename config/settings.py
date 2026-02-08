"""
Django settings for DjangoPress project.
Reusable CMS blueprint for AI-powered content generation.
"""

import environ
from pathlib import Path
from django.utils.translation import gettext_lazy as _
import warnings
import os

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
env = environ.Env()
env.read_env(BASE_DIR / '.env')

# Environment
ENVIRONMENT = env('ENVIRONMENT', default='development')

# Debug mode - can be overridden independently of environment
DEBUG_MODE = env('DEBUG_MODE', default='False') == 'True'

# Basic settings
SECRET_KEY = env('SECRET_KEY', default='django-insecure-372d0ca8799a3029769a1bc4297480e0df57630a1c11dbe9')

# Enable DEBUG if in development OR if DEBUG_MODE is explicitly enabled
DEBUG = ENVIRONMENT == 'development' or DEBUG_MODE

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*.railway.app']

# Site Configuration
SITE_NAME = "DjangoPress"

# Application definition
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
    'ai',
    'backoffice',
    'editor',
    'core',
    'news',
]

# Add whitenoise.runserver_nostatic only in production
if ENVIRONMENT != 'development':
    INSTALLED_APPS.insert(0, 'whitenoise.runserver_nostatic')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'core.middleware.DynamicLanguageMiddleware',  # Override default language from database
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.DomainMiddleware',
    'core.middleware.MaintenanceModeMiddleware',
]

ROOT_URLCONF = 'config.urls'

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
                'django.template.context_processors.i18n',
                'core.context_processors.site_settings',
            ],
            'debug': DEBUG,  # Enable template debug mode
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database - SQLite for both development and production
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en'  # Default language - should match SiteSettings default_language
LANGUAGES = [('en', 'English'), ('pt', 'Portuguese')]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Modeltranslation settings REMOVED - Now using JSON translations
# All translatable content is stored in JSONFields with structure:
# {"pt": "Portuguese text", "en": "English text"}
# See core.models for helper methods and core.templatetags.section_tags for template filters

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# STATICFILES_STORAGE depending on environment
if ENVIRONMENT == 'development':
    STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage'
    warnings.warn("Running in DEVELOPMENT mode. collectstatic is NOT required.")
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Production-only security settings
if ENVIRONMENT != 'development':
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = False
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Staticfiles backend for STORAGES
_staticfiles_backend = (
    "whitenoise.storage.StaticFilesStorage" if ENVIRONMENT == 'development'
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# Media files configuration — GCS if configured, local otherwise
if env('GS_BUCKET_NAME', default=''):
    from google.oauth2 import service_account
    import json

    GS_BUCKET_NAME = env('GS_BUCKET_NAME')
    GS_PROJECT_ID = env('GS_PROJECT_ID')

    MEDIA_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/'

    # Credentials setup - supports both file path and JSON string
    credentials_json = env('GCS_CREDENTIALS_JSON', default='')
    credentials_path = env('GS_CREDENTIALS_FILE_PATH', default='')

    if credentials_json:
        GS_CREDENTIALS = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json)
        )
    elif credentials_path:
        GS_CREDENTIALS_FILE_PATH = BASE_DIR / credentials_path
        GS_CREDENTIALS = service_account.Credentials.from_service_account_file(
            GS_CREDENTIALS_FILE_PATH
        )
    else:
        GS_CREDENTIALS = None

    GS_DEFAULT_ACL = None
    GS_FILE_OVERWRITE = False
    GS_MAX_MEMORY_SIZE = 5242880  # 5MB
    GS_QUERYSTRING_AUTH = False

    STORAGES = {
        "default": {
            "BACKEND": "config.storage_backends.DomainBasedStorage",
        },
        "staticfiles": {
            "BACKEND": _staticfiles_backend,
        },
    }
    DEFAULT_FILE_STORAGE = 'config.storage_backends.DomainBasedStorage'
else:
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": _staticfiles_backend,
        },
    }

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = [
    'http://localhost',
    'http://127.0.0.1',
    'https://*.railway.app',
]

# Authentication URLs
LOGIN_URL = '/backoffice/login/'
LOGIN_REDIRECT_URL = '/backoffice/'
LOGOUT_REDIRECT_URL = '/backoffice/login/'

# Email Configuration (Mailgun via Anymail)
if ENVIRONMENT == 'development':
    # Development: Print emails to console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # Production: Use Mailgun via Anymail
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
    ANYMAIL = {
        "MAILGUN_API_KEY": env('MAILGUN_API_KEY', default=''),
        "MAILGUN_API_URL": env('MAILGUN_API_URL', default='https://api.eu.mailgun.net/v3'),
    }

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@sendermail.io')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Logging configuration
ENABLE_DEBUG_LOGGING = env('ENABLE_DEBUG_LOGGING', default='False') == 'True'

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
    # Always show template errors even without debug logging enabled
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
