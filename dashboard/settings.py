"""
Django settings for dashboard project.
"""
from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from urllib.parse import quote_plus
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-i^pmp1x(gpyl*-l7j3wgv+9l8=w&g+ki2xfy(#)uee319p_-@c'

# True locally, False on Render (set DJANGO_DEBUG=False in Render env vars)
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') != 'False'

ALLOWED_HOSTS = [
    'dashboard-fcy3.onrender.com',
    'localhost',
    '127.0.0.1',
    '.vercel.app',
    'now.sh',
    'dashboard-mu-ten-50.vercel.app',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'marketing',
    'admin_panel',
    'exports',
    'channel',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

X_FRAME_OPTIONS = "SAMEORIGIN"

ROOT_URLCONF = 'dashboard.urls'

SESSION_COOKIE_AGE = 900
SESSION_SAVE_EVERY_REQUEST = True

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dashboard.wsgi.application'

# ── Database ──────────────────────────────────────────────────────────────────
# Supabase Postgres, connected via the SESSION POOLER (port 5432) — the right
# choice for Django's persistent connections. No local Postgres install needed:
# psycopg2-binary is a self-contained client library, not a database server.
#
# Password is kept in an env var and URL-encoded automatically, so special
# characters (@ $ # : / etc.) never break the connection string. In .env put
# the password RAW (no encoding) as DB_PASSWORD — quote_plus() encodes it here.
#
# Priority:
#   1. DATABASE_URL env var, if set (paste the full string on Render)
#   2. Otherwise, build the Supabase URL from DB_PASSWORD
#   3. If neither is available, fall back to local SQLite (keeps local dev
#      working even with no .env configured)

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

SUPABASE_DATABASE_URL = (
    f"postgresql://postgres.qrdegkvnalvmbbwsbyto:{quote_plus(DB_PASSWORD)}"
    f"@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
) if DB_PASSWORD else None

_default_db_url = os.environ.get(
    'DATABASE_URL',
    SUPABASE_DATABASE_URL or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
)

DATABASES = {
    'default': dj_database_url.config(
        default=_default_db_url,
        conn_max_age=600,          # reuse connections instead of reopening each request
        conn_health_checks=True,   # drop dead connections automatically
    )
}

# ── Cache ─────────────────────────────────────────────────────────────────────
# Redis when REDIS_URL is set — fast, shared across worker processes, survives
# restarts. A free web-signup option with no local install is Upstash
# (upstash.com) or Render's own Key Value add-on; either gives you a REDIS_URL
# to paste into your environment variables. Falls back to per-process
# in-memory cache if REDIS_URL isn't set, so local dev still works untouched.
REDIS_URL = os.environ.get('REDIS_URL', '')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'TIMEOUT': 300,   # default 5-minute cache lifetime
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'TIMEOUT': 300,
        }
    }

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── Media files ───────────────────────────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Web Push (VAPID) ──────────────────────────────────────────────────────────
# Generate keys once: python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.public_key.decode(),v.private_key.decode())"
VAPID_PUBLIC_KEY  = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS      = {'sub': f'mailto:{os.environ.get("ADMIN_EMAIL", "admin@example.com")}'}