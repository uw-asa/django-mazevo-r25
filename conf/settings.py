import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

SECRET_KEY = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

DEBUG = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'mazevo_r25',
]

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.PersistentRemoteUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.RemoteUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'conf.urls'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/Los_Angeles'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_ROOT = ''
STATIC_URL = '/static/'

AUTHZ_GROUP_BACKEND = \
    'authz_group.authz_implementation.uw_group_service.UWGroupService'

EVENT_SCHEDULER_GROUP = 'uw_asa_it_events_schedulers'

# A saved search, which we automatically maintain
MAZEVO_R25_SPACE_QUERY = '999'

# Statuses to ignore entirely
MAZEVO_R25_IGNORE_STATUSES = [
    'Academic Confirmed',
    'Academic Conflict',
    'Academic Crosslist',
]

# Statuses for which R25 Reservations will not be made, or if already existing,
# will be cancelled. These are in addition to any status which isn't of the
# "Booked Space" Status Type.
MAZEVO_R25_REMOVE_STATUSES = [
    'Blackout',
    'Requested',
    'Tentative',
    'Tentative PCS',
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'mazevo_r25': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
