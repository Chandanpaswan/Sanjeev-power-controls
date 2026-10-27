"""Django settings for Sanjeev Power Controls.

Values that change between environments live in environment variables.
Copy `.env.example` to `.env` for local development.
"""
from pathlib import Path
import os
import urllib.parse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# `.env` is the local development file. `.env.local` is written by the Vercel
# and Neon CLIs; existing environment variables always win over both.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local")


def env(name, default=""):
    return os.environ.get(name, default).strip()


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-demo-only-change-me-before-deploying"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG=False."
        )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "accounts",
    "cms",
    "core",
    "email_manager",
    "products",
    "enquiries",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.MaintenanceModeMiddleware",
    "core.middleware.AdminRedirectMiddleware",
]

AUTH_USER_MODEL = "auth.User"  # Revert to default User to avoid conflicts

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_context",
                "core.context_processors.dashboard_context",
                "cms.context_processors.site_content",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — SQLite by default, PostgreSQL through DATABASE_URL or DB_* values
# ---------------------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL")
DB_ENGINE = env("DB_ENGINE")

if DATABASE_URL:
    # Single-URL form used by hosting platforms such as Vercel and Neon, e.g.
    # postgresql://user:pass@host/db?sslmode=require
    parsed = urllib.parse.urlparse(DATABASE_URL)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            "DATABASE_URL must use the postgres:// or postgresql:// scheme."
        )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": urllib.parse.unquote(parsed.username or ""),
            "PASSWORD": urllib.parse.unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
            # Serverless platforms pool connections through PgBouncer, which is
            # incompatible with server-side cursors in transaction mode.
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": dict(urllib.parse.parse_qsl(parsed.query)),
        }
    }
elif DB_ENGINE:
    if DB_ENGINE not in {
        "django.db.backends.postgresql",
        "django.db.backends.mysql",
    }:
        raise ImproperlyConfigured("Unsupported DB_ENGINE value.")
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": env("DB_NAME", "spc"),
            "USER": env("DB_USER", ""),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", ""),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / env("DB_NAME", "db.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
# Writable location for uploads. Vercel only allows writes under /tmp.
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
# Demo/preview deployments can serve uploads through Django when no object
# storage is configured. Disable once media is hosted elsewhere.
SERVE_MEDIA = env_bool("SERVE_MEDIA", DEBUG)

# Dashboard database/dump backups. Kept outside MEDIA_ROOT so archives are never
# served publicly; downloads are restricted to superusers.
BACKUP_DIR = BASE_DIR / env("BACKUP_DIR", "backups")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Uploaded product images are capped in the form; this is a defence-in-depth limit.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Session hardening. Staff sessions expire after 12 hours of inactivity.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", str(60 * 60 * 12)))
SESSION_SAVE_EVERY_REQUEST = True

# Cache-backed sign-in lockout (5 failures in 15 minutes).
LOGIN_MAX_ATTEMPTS = int(env("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(env("LOGIN_LOCKOUT_SECONDS", "900"))
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "spc-dashboard-cache",
    }
}
# For multi-process production deployments, replace the cache above with a
# shared Redis/Memcached backend so the login lockout applies across workers.

IMAGE_MAX_BYTES = 3 * 1024 * 1024
MEDIA_MAX_BYTES = 5 * 1024 * 1024

# Bootstrap-friendly message classes.
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}

# ---------------------------------------------------------------------------
# Production hardening
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    if env_bool("USE_X_FORWARDED_PROTO", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

X_FRAME_OPTIONS = globals().get("X_FRAME_OPTIONS", "SAMEORIGIN")
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{levelname} {asctime} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", "no-reply@sanjeevpowercontrols.example"
)
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587") or 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "20") or 20)
ADMIN_NOTIFICATION_EMAIL = env("ADMIN_NOTIFICATION_EMAIL", "")

# ---------------------------------------------------------------------------
# Email Manager
# ---------------------------------------------------------------------------
# Database-backed SMTP credentials are encrypted with this key. It must live
# outside the database and the repository. Use a Fernet key or a long random
# passphrase. In DEBUG mode a key derived from DJANGO_SECRET_KEY is used as a
# local-only fallback.
EMAIL_ENCRYPTION_KEY = env("EMAIL_ENCRYPTION_KEY", "")

# "database" sends through the SMTP settings saved in the dashboard.
# "django" uses EMAIL_BACKEND (used by automated tests with the in-memory
# backend, and available for environment-only deployments).
EMAIL_MANAGER_TRANSPORT = env("EMAIL_MANAGER_TRANSPORT", "database").lower()
if EMAIL_MANAGER_TRANSPORT not in {"database", "django"}:
    raise ImproperlyConfigured(
        "EMAIL_MANAGER_TRANSPORT must be 'database' or 'django'."
    )

# Total attempts = 1 + EMAIL_MANAGER_AUTO_RETRIES. Only transient connection
# failures are retried automatically; every attempt is counted on the email log.
EMAIL_MANAGER_MAX_ATTEMPTS = int(env("EMAIL_MANAGER_MAX_ATTEMPTS", "3") or 3)
EMAIL_MANAGER_AUTO_RETRIES = int(env("EMAIL_MANAGER_AUTO_RETRIES", "1") or 1)
EMAIL_MANAGER_RETRY_DELAY = float(env("EMAIL_MANAGER_RETRY_DELAY", "2") or 2)
EMAIL_LOG_RETENTION_DAYS = int(env("EMAIL_LOG_RETENTION_DAYS", "180") or 180)

# Used to build absolute links in emails sent outside a request (for example by
# a management command). Set this to the public HTTPS origin in production.
SITE_BASE_URL = env("SITE_BASE_URL", "")

handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
