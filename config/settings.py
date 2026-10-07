"""Environment-driven configuration. Production configuration fails closed."""
import hashlib
import os
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name, default=False):
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ImproperlyConfigured(f"{name} must be true or false.")
    return value in {"true", "1", "yes"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "development-only-key-never-use-this-value-for-a-public-deployment"
    else:
        raise ImproperlyConfigured("Set a unique SECRET_KEY before running in production.")
if not DEBUG and (len(SECRET_KEY) < 43 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("development-")):
    raise ImproperlyConfigured("Production SECRET_KEY must be a random value of at least 256 bits (43+ encoded characters).")
# Render's generateValue produces a 44-character base64 256-bit secret. Derive
# a fixed-length Django key without reducing entropy; this also satisfies
# Django's deployment check, which uses a minimum textual length of 50.
SECRET_KEY = hashlib.sha512(SECRET_KEY.encode("utf-8")).hexdigest()

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else RENDER_HOST)
if RENDER_HOST and RENDER_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_HOST)
if not ALLOWED_HOSTS or any(host == "*" or host.startswith(".") or "/" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("ALLOWED_HOSTS must contain exact hostnames, without schemes or wildcards.")

SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000" if DEBUG else (f"https://{RENDER_HOST}" if RENDER_HOST else "")).rstrip("/")
site_parts = urlsplit(SITE_URL)
if not site_parts.netloc or site_parts.username or site_parts.password or site_parts.query or site_parts.fragment or site_parts.path or site_parts.scheme not in ({"http", "https"} if DEBUG else {"https"}):
    raise ImproperlyConfigured("SITE_URL must be your complete site origin, HTTPS in production, without a path.")
if site_parts.hostname not in ALLOWED_HOSTS:
    raise ImproperlyConfigured("The SITE_URL hostname must appear in ALLOWED_HOSTS.")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", SITE_URL)
if not DEBUG and any(not origin.startswith("https://") or "*" in origin for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Production CSRF_TRUSTED_ORIGINS must contain exact HTTPS origins.")

INSTALLED_APPS = [
    "config.apps.EidrenAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "axes",
    "config.apps.PlatformConfig",
    "shop.apps.ShopConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "shop.context_processors.store_context",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

database_url = os.getenv("DATABASE_URL", "")
if database_url:
    DATABASES = {"default": dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3", "OPTIONS": {"timeout": 20}}}
if not DEBUG:
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL. SQLite is development-only.")
    if env_bool("DATABASE_REQUIRE_SSL", True):
        DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"

AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 14}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS = True
AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
AXES_CLIENT_IP_CALLABLE = "config.security.client_ip"
AXES_LOCKOUT_CALLABLE = "config.security.lockout_response"
AXES_ENABLE_ACCESS_FAILURE_LOG = False
AXES_SENSITIVE_PARAMETERS = ["username", "ip_address", "password", "otp_token"]
TRUSTED_PROXY_CIDRS = env_list("TRUSTED_PROXY_CIDRS")
OTP_TOTP_ISSUER = "EIDREN Admin"
OTP_TOTP_THROTTLE_FACTOR = 2
OTP_STATIC_THROTTLE_FACTOR = 2
OTP_ADMIN_HIDE_SENSITIVE_DATA = True

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
# Enable this only when your ingress strips/replaces X-Forwarded-Proto.
# Render terminates TLS at its managed ingress; a standalone deployment is not trusted by default.
if env_bool("TRUST_PROXY_SSL", bool(RENDER_HOST)):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500

STORE_NAME = os.getenv("STORE_NAME", "EIDREN")
STORE_EMAIL = os.getenv("STORE_EMAIL", "concierge@example.com")
DEFAULT_FROM_EMAIL = STORE_EMAIL
SERVER_EMAIL = STORE_EMAIL
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_AUTOMATIC_TAX = env_bool("STRIPE_AUTOMATIC_TAX", False)
DEMO_MODE = env_bool("DEMO_MODE", DEBUG)
SHIPPING_COUNTRIES = [value.upper() for value in env_list("SHIPPING_COUNTRIES", "US")]
if not SHIPPING_COUNTRIES or any(not re.fullmatch(r"[A-Z]{2}", code) for code in SHIPPING_COUNTRIES):
    raise ImproperlyConfigured("SHIPPING_COUNTRIES must contain comma-separated two-letter country codes.")
try:
    SHIPPING_RATE_CENTS = int(os.getenv("SHIPPING_RATE_CENTS", "0"))
except ValueError as exc:
    raise ImproperlyConfigured("SHIPPING_RATE_CENTS must be a non-negative integer.") from exc
if not 0 <= SHIPPING_RATE_CENTS <= 100000:
    raise ImproperlyConfigured("SHIPPING_RATE_CENTS must be between 0 and 100000.")
if DEMO_MODE and STRIPE_SECRET_KEY.startswith("sk_live_"):
    raise ImproperlyConfigured("Live Stripe keys cannot be used while DEMO_MODE is enabled.")

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.security": {"level": "WARNING"}, "axes": {"level": "WARNING"}},
}
