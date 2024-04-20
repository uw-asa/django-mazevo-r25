import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

SECRET_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

DEBUG = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "mazevo_r25",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.PersistentRemoteUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.RemoteUserBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "conf.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
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

LANGUAGE_CODE = "en-us"

TIME_ZONE = "America/Los_Angeles"

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_ROOT = ""
STATIC_URL = "/static/"

AUTHZ_GROUP_BACKEND = "authz_group.authz_implementation.uw_group_service.UWGroupService"

EVENT_SCHEDULER_GROUP = "uw_asa_it_events_schedulers"

# Statuses to ignore entirely
MAZEVO_R25_IGNORE_STATUSES = [
    "Academic Confirmed",
    "Academic Conflict",
    "Academic Crosslist",
]

# Statuses for which R25 Reservations will not be made, or if already
# existing, will be cancelled. These are in addition to any status
# which doesn't "Block Space".
MAZEVO_R25_REMOVE_STATUSES = [
    "Blackout",
    "Requested",
    "Tentative",
    "Tentative PCS",
]

# Map Mazevo Booking Status to R25 Event Type
MAZEVO_R25_EVENTTYPE_DEFAULT = "433"  # UWS Event
MAZEVO_R25_EVENTTYPE_MAP = {
    "Academic Final Exam": "475",  # UWS ES_Final
    "CAAMS Booking": "467",  # UWS CAAMS
    "Blackout": "416",  # Repair/Maintenance
    "Event Finalized (DAX Bypass)": "416",  # Repair/Maintenance
}

MAZEVO_R25_EMAIL_HOST_USER = ""
MAZEVO_R25_EMAIL_HOST_PASSWORD = ""
MAZEVO_R25_EMAIL_RECIPIENTS = ""

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "mazevo_r25": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
    },
}
