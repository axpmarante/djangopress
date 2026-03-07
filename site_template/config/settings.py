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

# --- Site-specific apps (uncomment to add) ---
# INSTALLED_APPS += ['my_app']
