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

MAZEVO_R25_ORGANIZATION = ""

# R25 event types for courses to import to Mazevo
MAZEVO_R25_EVENTTYPE_TS_SECTION = 459
MAZEVO_R25_EVENTTYPE_TS_SECTION_FINAL = 472

# Default R25 event type for bookings imported from Mazevo
MAZEVO_R25_EVENTTYPE_DEFAULT = '433'    # UWS Event

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
