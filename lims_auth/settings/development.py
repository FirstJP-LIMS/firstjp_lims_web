from .base import *

DEBUG = True


INSTALLED_APPS += ["debug_toolbar"]

MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

INTERNAL_IPS = ["127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


PLATFORM_BASE_DOMAIN = "localhost.test"  # Used for domain generation
GLOBAL_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".localhost.test",
]

ALLOWED_HOSTS = GLOBAL_HOSTS


