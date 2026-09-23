"""
Django settings for the Analisis Ejecutivos project.

Mirrors the conventions of ControlPresupuestos_AP (env-driven, _DEV suffix
for the dev database, optional URL prefix when reverse-proxied, WhiteNoise +
Waitress in production). One deliberate difference: the .env lives at
config/.env, not core/config/.env, because this repo has no `core` package
(the standalone scripts in scripts/ import the Wansoft repo's own `core`
package, and two packages with the same name would collide).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(dotenv_path=BASE_DIR / "config" / ".env")

ENV = os.getenv("ENV", "prod").lower()

# SECURITY WARNING: keep the secret key used in production secret!
# There is no insecure fallback on purpose: production must never boot with
# a key committed to git. Set DJANGO_SECRET_KEY in config/.env (see
# config/.env.example for how to generate one).
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DJANGO_DEBUG", "true" if ENV == "dev" else "false").lower() == "true"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

# Set only when this app is reverse-proxied under a URL prefix (Apache maps
# http://host:8088/analisis_ejecutivos/ -> this app's root). Makes every URL
# Django generates come out with that prefix. Leave unset for dev.
FORCE_SCRIPT_NAME = os.getenv("DJANGO_FORCE_SCRIPT_NAME") or None

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "cuentas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: this app's own database (users, profiles, subscriptions, send
# log) lives on the separate database server, never on the app machine.
# Report DATA is read elsewhere (Odoo / the productive Wansoft MySQL), not here.
_DB_SUFFIX = "_DEV" if ENV == "dev" else ""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "HOST": os.getenv(f"EJECUTIVOS_DB_HOST{_DB_SUFFIX}"),
        "PORT": os.getenv(f"EJECUTIVOS_DB_PORT{_DB_SUFFIX}", "3306"),
        "USER": os.getenv(f"EJECUTIVOS_DB_USER{_DB_SUFFIX}"),
        "PASSWORD": os.getenv(f"EJECUTIVOS_DB_PASSWORD{_DB_SUFFIX}"),
        "NAME": os.getenv(f"EJECUTIVOS_DB_NAME{_DB_SUFFIX}"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = f"{FORCE_SCRIPT_NAME or ''}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"

# Session/cookie hardening. Secure cookies only make sense over HTTPS, so
# they are enabled only when explicitly requested (the proxy currently
# serves plain http on :8088 -- flip DJANGO_SECURE_COOKIES=true once HTTPS
# is in front of it).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours
_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "false").lower() == "true"
SESSION_COOKIE_SECURE = _SECURE
CSRF_COOKIE_SECURE = _SECURE
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Email (report delivery lands in a later phase; console backend until then).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "django.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {"level": "INFO", "class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
