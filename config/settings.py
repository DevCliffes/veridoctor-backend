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
    # FRONTEND_URLS env var on Render — comma-separated list of allowed origins.
    # Example value:
    #   https://veridoctor-client-1f6x4an5o-dev-cliffes-projects.vercel.app,https://veridoctor-client-ffs7ue4ah-dev-cliffes-projects.vercel.app
    CORS_ALLOWED_ORIGINS = [
        url.strip()
        for url in os.getenv("FRONTEND_URLS", "").split(",")
        if url.strip()
    ]

    # FIX: CSRF_TRUSTED_ORIGINS previously only included the frontend URLs.
    # That left the backend's own domain (where /admin/login/ is served from)
    # untrusted, so Django rejected the admin login POST with
    # "Forbidden (403) CSRF verification failed." Added BACKEND_URL below.
    CSRF_TRUSTED_ORIGINS = [
        url.strip()
        for url in os.getenv("FRONTEND_URLS", "").split(",")
        if url.strip()
    ] + [
        url.strip()
        for url in os.getenv(
            "BACKEND_URL", "https://veridoctor-backend-1.onrender.com"
        ).split(",")
        if url.strip()
    ]

    # Regex that matches ANY Vercel preview deployment for this project so you
    # never have to update FRONTEND_URLS again when Vercel generates a new URL.
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^https://veridoctor-client-[a-z0-9]+-dev-cliffes-projects\.vercel\.app$",
    ]

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
    "records",
    "notifications",
]

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        # 'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
        # NOTE: left empty intentionally for now — switching this to
        # IsAuthenticated globally will start rejecting requests, and
        # should only happen once we've confirmed the frontend attaches
        # the access token as an Authorization header on every request.
        # See JWTAuthentication below for how it expects the token.
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "identity.authentication.JWTAuthentication",
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
        "DIRS": [BASE_DIR / "templates"],
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
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"  # For prod
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


# ──────────────────────────────────────────────
# DJANGO UNFOLD ADMIN — BRANDING & DASHBOARD CONFIG
# ──────────────────────────────────────────────
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": "VeriDoctor Admin",
    "SITE_HEADER": "VeriDoctor",
    "SITE_SUBHEADER": "Healthcare Platform Administration",
    "SITE_URL": "/",
    # Uncomment once you have logo files placed in a static/images/ folder:
    # "SITE_ICON": lambda request: static("images/logo-icon.png"),
    # "SITE_LOGO": lambda request: static("images/logo.png"),
    "SITE_SYMBOL": "local_hospital",  # Material icon shown when no logo is set
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "ENVIRONMENT": "config.unfold_helpers.environment_callback",
    "DASHBOARD_CALLBACK": "config.unfold_helpers.dashboard_callback",
    "COLORS": {
        "primary": {
            "50": "240 253 244",
            "100": "220 252 231",
            "200": "187 247 208",
            "300": "134 239 172",
            "400": "74 222 128",
            "500": "22 163 74",   # core brand green
            "600": "16 138 62",
            "700": "15 109 51",
            "800": "14 86 42",
            "900": "12 71 36",
            "950": "5 40 20",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Overview"),
                "separator": True,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": _("Appointments"),
                "separator": True,
                "items": [
                    {
                        "title": _("Provider appointments"),
                        "icon": "event",
                        "link": reverse_lazy(
                            "admin:appointments_providerappointment_changelist"
                        ),
                    },
                ],
            },
            {
                "title": _("People"),
                "separator": True,
                "items": [
                    {
                        "title": _("Patient accounts"),
                        "icon": "person",
                        "link": reverse_lazy(
                            "admin:identity_patientaccount_changelist"
                        ),
                    },
                    {
                        "title": _("Healthcare provider accounts"),
                        "icon": "medical_services",
                        "link": reverse_lazy(
                            "admin:identity_healthcareprovideraccount_changelist"
                        ),
                    },
                    {
                        "title": _("Healthcare providers"),
                        "icon": "stethoscope",
                        "link": reverse_lazy(
                            "admin:provider_healthcareprovider_changelist"
                        ),
                    },
                    {
                        "title": _("Facility manager accounts"),
                        "icon": "admin_panel_settings",
                        "link": reverse_lazy(
                            "admin:identity_facilitymanageraccount_changelist"
                        ),
                    },
                    {
                        "title": _("Branch manager accounts"),
                        "icon": "supervisor_account",
                        "link": reverse_lazy(
                            "admin:identity_branchmanageraccount_changelist"
                        ),
                    },
                    {
                        "title": _("Identities"),
                        "icon": "badge",
                        "link": reverse_lazy("admin:identity_identity_changelist"),
                    },
                    {
                        "title": _("OTPs"),
                        "icon": "pin",
                        "link": reverse_lazy("admin:identity_otp_changelist"),
                    },
                ],
            },
            {
                "title": _("Facilities"),
                "separator": True,
                "items": [
                    {
                        "title": _("Facilities"),
                        "icon": "apartment",
                        "link": reverse_lazy("admin:facility_facility_changelist"),
                    },
                    {
                        "title": _("Workstations"),
                        "icon": "desktop_windows",
                        "link": reverse_lazy("admin:facility_workstation_changelist"),
                    },
                ],
            },
        ],
    },
}
