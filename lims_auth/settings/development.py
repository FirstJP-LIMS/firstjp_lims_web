from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    '127.1.0.0',
    '.localhost.test',
    'carboni1.localhost',
    '.localhost',
]

INSTALLED_APPS += ["debug_toolbar"]

MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

INTERNAL_IPS = ["127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

PLATFORM_BASE_DOMAIN = "localhost.test"
GLOBAL_HOSTS = ['127.0.0.1', 'localhost', '127.1.0.0', PLATFORM_BASE_DOMAIN]
