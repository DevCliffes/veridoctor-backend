"""
The core settings module
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-k8ea2gs4%f)3*9bix^yjfax9r@o9+arjo)7e@s2@$y##a8k*x0",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DJANGO_DEBUG_MODE", "True") == "True"

if DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
else:
    ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

# CORS SETTINGS
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = os.getenv("FRONTEND_URLS", "").split(",")
    CSRF_TRUSTED_ORIGINS = os.getenv("FRONTEND_URLS", "").split(",")
    CSRF_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_DOMAIN = None
    SESSION_COOKIE_SAMESITE = "None"

CORS_ALLOW_CREDENTIALS = True
CORS_PREFLIGHT_MAX_AGE = 86400  # 1 day

# Application definition
INSTALLED_APPS = [
    "unfold",  # for django admin panel
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "identity",
    "facility",
    "provider",
    "scheduling",
    "appointments",
    "shared",
]

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        # 'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # serving static assets in admin
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("PG_DATABASE_HOST"),
        "PORT": os.getenv("PG_DATABASE_PORT"),
    }
}

# SECRETS
JWT_SECRET = os.getenv("JWT_SECRET")
# EMAIL SETTINGS
# SMTP server config
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # For dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # For prod
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = os.getenv("EMAIL_PORT")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
# EMAIL HOST AND PASSWORD
EMAIL_HOST_USER = os.getenv("NOREPLY_EMAIL")
EMAIL_HOST_PASSWORD = os.getenv("NOREPLY_EMAIL_PASSWORD")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Nairobi"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# file upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# security settings for production
if not DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = False
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Default auth user model
AUTH_USER_MODEL = "identity.Identity"
