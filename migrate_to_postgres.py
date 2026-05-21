"""
migrate_to_postgres.py

Run from your project root:
    python migrate_to_postgres.py

This directly reads from SQLite and writes to PostgreSQL in batches.
No JSON serialization involved — bypasses all encoding issues.
"""

import os
import sys
import django

# ── Setup Django ─────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')

# We need to swap databases at runtime
# First collect data from SQLite, then push to Postgres
import django.conf

django.setup()

from django.db import connections
from django.contrib.auth.models import User, Group
from django.contrib.auth.models import Permission

# ── Config ───────────────────────────────────────────────────
import os
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qsl

load_dotenv()
_db_url = urlparse(os.getenv("DATABASE_URL", ""))

POSTGRES = {
    'ENGINE':    'django.db.backends.postgresql',
    'NAME':      _db_url.path.replace('/', ''),
    'USER':      _db_url.username,
    'PASSWORD':  _db_url.password,
    'HOST':      _db_url.hostname,
    'PORT':      5432,
    'OPTIONS':   dict(parse_qsl(_db_url.query)),
    'TIME_ZONE': None,
    'CONN_MAX_AGE': 0,
    'CONN_HEALTH_CHECKS': False,
    'AUTOCOMMIT': True,
    'ATOMIC_REQUESTS': False,
    'TEST': {'NAME': None},
}

BATCH = 500   # rows per insert batch

# ── Add postgres as a second DB connection ────────────────────
from django.conf import settings
settings.DATABASES['postgres_target'] = POSTGRES

# ── Helpers ──────────────────────────────────────────────────
def migrate_model(Model, db_source='default', db_target='postgres_target', batch=BATCH):
    name = Model.__name__
    total = Model.objects.using(db_source).count()
    if total == 0:
        print(f"  {name}: 0 rows — skipped")
        return

    print(f"  {name}: {total} rows ... ", end='', flush=True)
    Model.objects.using(db_target).all().delete()

    offset = 0
    while offset < total:
        chunk = list(Model.objects.using(db_source).all()[offset:offset+batch])
        # Strip PKs for through tables to avoid conflicts; keep for main models
        for obj in chunk:
            obj._state.db = db_target
        Model.objects.using(db_target).bulk_create(chunk, ignore_conflicts=True)
        offset += batch

    done = Model.objects.using(db_target).count()
    print(f"done ({done} rows)")

# ── Run migrations on Postgres first ─────────────────────────
print("Step 1: Running migrations on PostgreSQL...")
from django.core.management import call_command
call_command('migrate', '--database=postgres_target', verbosity=0)
print("  Migrations complete.\n")

# ── Migrate each model ────────────────────────────────────────
print("Step 2: Copying data...\n")

# Auth models
try:
    migrate_model(User)
except Exception as e:
    print(f"  User: ERROR — {e}")

# Marketing app
try:
    from marketing.models import SiteData, UserProfile, ChatMessage
    migrate_model(SiteData)
    migrate_model(UserProfile)
    migrate_model(ChatMessage)
except ImportError as e:
    print(f"  Marketing models: {e}")
except Exception as e:
    print(f"  Marketing: ERROR — {e}")

# Channel app
try:
    from channel.models import ChannelDaily
    migrate_model(ChannelDaily)
except ImportError as e:
    print(f"  Channel models: {e}")
except Exception as e:
    print(f"  Channel: ERROR — {e}")

print("\nStep 3: Verifying row counts...")
models_to_check = []
try:
    from marketing.models import SiteData, UserProfile
    models_to_check += [SiteData, UserProfile]
except: pass
try:
    from channel.models import ChannelDaily
    models_to_check.append(ChannelDaily)
except: pass

for Model in models_to_check:
    src = Model.objects.using('default').count()
    dst = Model.objects.using('postgres_target').count()
    status = "✓" if src == dst else "✗ MISMATCH"
    print(f"  {status} {Model.__name__}: SQLite={src}, PostgreSQL={dst}")

print("\nDone! Now update your settings.py DATABASES to point to PostgreSQL.")
print("Then run: python manage.py migrate")