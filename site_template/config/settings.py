"""
Site settings — imports DjangoPress defaults and applies local overrides.
"""
from djangopress.settings import *  # noqa: F401,F403

import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
env.read_env(BASE_DIR / '.env')

# --- Required overrides ---
SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me')
ENVIRONMENT = env('ENVIRONMENT', default='development')
DEBUG_MODE = env('DEBUG_MODE', default='False') == 'True'
DEBUG = ENVIRONMENT == 'development' or DEBUG_MODE

# --- URL and WSGI config ---
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# --- Database ---
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# --- Paths ---
TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates'] + TEMPLATES[0]['DIRS']
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'
LOCALE_PATHS = [BASE_DIR / 'locale']

# --- Whitenoise ---
if ENVIRONMENT == 'development':
    STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage'
else:
    INSTALLED_APPS.insert(0, 'whitenoise.runserver_nostatic')
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Storage ---
_staticfiles_backend = (
    'whitenoise.storage.StaticFilesStorage' if ENVIRONMENT == 'development'
    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
)

if env('GS_BUCKET_NAME', default=''):
    from google.oauth2 import service_account
    import json

    GS_BUCKET_NAME = env('GS_BUCKET_NAME')
    GS_PROJECT_ID = env('GS_PROJECT_ID')
    MEDIA_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/'

    credentials_json = env('GCS_CREDENTIALS_JSON', default='')
    credentials_path = env('GS_CREDENTIALS_FILE_PATH', default='')
    if credentials_json:
        GS_CREDENTIALS = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json)
        )
    elif credentials_path:
        GS_CREDENTIALS = service_account.Credentials.from_service_account_file(
            BASE_DIR / credentials_path
        )
    else:
        GS_CREDENTIALS = None

    GS_DEFAULT_ACL = None
    GS_FILE_OVERWRITE = False
    GS_MAX_MEMORY_SIZE = 5242880
    GS_QUERYSTRING_AUTH = False

    STORAGES = {
        'default': {'BACKEND': 'djangopress.storage_backends.DomainBasedStorage'},
        'staticfiles': {'BACKEND': _staticfiles_backend},
    }
    DEFAULT_FILE_STORAGE = 'djangopress.storage_backends.DomainBasedStorage'
else:
    MEDIA_URL = '/media/'
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': _staticfiles_backend},
    }

# --- Email ---
if ENVIRONMENT == 'development':
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'
    ANYMAIL = {
        'MAILGUN_API_KEY': env('MAILGUN_API_KEY', default=''),
        'MAILGUN_API_URL': env('MAILGUN_API_URL', default='https://api.eu.mailgun.net/v3'),
    }

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@sendermail.io')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- API keys ---
UNSPLASH_ACCESS_KEY = env('UNSPLASH_ACCESS_KEY', default='')
USE_REFINEMENT_AGENT = env('USE_REFINEMENT_AGENT', default='True') == 'True'

# --- Site-specific apps (uncomment to add) ---
# INSTALLED_APPS += ['my_app']
