# -*- coding: utf-8 -*-

# Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid

# This file is part of WStore.

# WStore is free software: you can redistribute it and/or modify
# it under the terms of the European Union Public Licence (EUPL)
# as published by the European Commission, either version 1.1
# of the License, or (at your option) any later version.

# WStore is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# European Union Public Licence for more details.

# You should have received a copy of the European Union Public Licence
# along with WStore.
# If not, see <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>.

# NOTE: Differences to settings_template.py
#        - Uses suburl /store
#        - All run time data is placed to <root>/data

from os import path

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django_mongodb_engine',  # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'wstore_db',           # Or path to database file if using sqlite3.
        'USER': '',                         # Not used with sqlite3.
        'PASSWORD': '',                     # Not used with sqlite3.
        'HOST': '',                         # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                         # Set to empty string for default. Not used with sqlite3.
        'TEST_NAME': 'test_database',
    }
}

BASEDIR = path.dirname(path.abspath(__file__)) # src/
DATADIR = path.join(path.dirname(BASEDIR), 'data') # ../src/data

STORE_NAME = 'WStore'
AUTH_PROFILE_MODULE = 'wstore.models.UserProfile'
PORTALINSTANCE = False
OILAUTH = True

# Language code for this installation.
LANGUAGE_CODE = 'en'

SITE_ID=u''

BASE_URL = '/store/'

# Absolute filesystem path to the directory that will hold user-uploaded files.
MEDIA_ROOT = path.join(DATADIR, 'media')

BILL_ROOT = path.join(MEDIA_ROOT, 'bills')

# URL that handles the media served from MEDIA_ROOT.
MEDIA_URL = BASE_URL + 'media/'

# Absolute path to the directory static files should be collected to.
STATIC_ROOT = path.join(DATADIR, 'static')

# URL prefix for static files.
STATIC_URL = BASE_URL + 'static/'

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django_mongodb_engine',
    'djangotoolbox',
    'wstore',
    'ui.fiware.defaulttheme',
    'ui.fiware', # or ui.fiware
    'wstore.charging_engine',
    'wstore.store_commons',
    'wstore.social.tagging',
    'django_crontab',
    'django_nose',
    'social_auth',
    'wstore.registration'
)

# Create a testing variable containing whether django is in testing mode
import sys
TESTING = sys.argv[1:2] == ['test']

# Load test_settings if testing
if TESTING and 'wstore.selenium_tests' in INSTALLED_APPS:
    from wstore.selenium_tests.test_settings import *

if OILAUTH:
    LOGIN_URL = BASE_URL + "login/fiware/"
    LOGIN_REDIRECT_URL = BASE_URL
    LOGIN_ERROR_URL = BASE_URL + 'login-error'
    SOCIAL_AUTH_DISCONNECT_REDIRECT_URL = BASE_URL + "login/fiware/"
else:
    LOGIN_URL = BASE_URL + 'login/'

USDL_EDITOR_URL = "http://store.lab.fi-ware.eu/usdl-editor"

# Make this unique, and don't share it with anybody.
SECRET_KEY = '8p509oqr^68+z)y48_*pv!ceun)gu7)yw6%y9j2^0=o14)jetr'

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.request',
    'django.core.context_processors.static',
    'social_auth.context_processors.social_auth_by_type_backends',
)

SOCIAL_AUTH_PIPELINE = (
    'social_auth.backends.pipeline.social.social_auth_user',
    #'social_auth.backends.pipeline.associate.associate_by_email',
    'social_auth.backends.pipeline.user.get_username',
    'social_auth.backends.pipeline.user.create_user',
    'social_auth.backends.pipeline.social.associate_user',
    'social_auth.backends.pipeline.social.load_extra_data',
    'social_auth.backends.pipeline.user.update_user_details',
    'wstore.social_auth_backend.fill_internal_user_info'
)

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
#    'wstore.themes.load_template_source',
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'wstore.store_commons.middleware.URLMiddleware',
)

WSTOREMAILUSER = '<mail_user>'
WSTOREMAIL = '<email>'
WSTOREMAILPASS = '<email_passwd>'
SMTPSERVER = 'smtp.gmail.com:587'

WSTOREPROVIDERREQUEST = '<provider_requests_email>'

URL_MIDDLEWARE_CLASSES = {
    'default': (
        'django.middleware.common.CommonMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'wstore.store_commons.middleware.ConditionalGetMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
    ),
    'api': (
        'django.middleware.common.CommonMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'wstore.store_commons.middleware.ConditionalGetMiddleware',
        'wstore.store_commons.middleware.AuthenticationMiddleware',
    ),
    'media': (
        'django.middleware.common.CommonMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'wstore.store_commons.middleware.ConditionalGetMiddleware',
        'wstore.store_commons.middleware.AuthenticationMiddleware',
    )
}

ROOT_URLCONF = 'urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'wsgi.application'

# Payment method determines the payment gateway to be used
# Allowed values: paypal, fipay, None (default)
PAYMENT_METHOD = None

ACTIVATION_DAYS = 2

AUTHENTICATION_BACKENDS = (
    'wstore.social_auth_backend.FiwareBackend',
    'django.contrib.auth.backends.ModelBackend',
)

# Config instructions:
#http://forge.fiware.org/plugins/mediawiki/wiki/fiware/index.php/Store_-_W-Store_-_Installation_and_Administration_Guide#FI-WARE_Identity_management

FIWARE_APP_ID = '<app_id>'
FIWARE_API_SECRET = '<app_secret>'
# NOTE: If endpoint is more than server name, remember to add '/' to end or last part will be lost.
FIWARE_IDM_ENDPOINT = 'https://account.lab.fi-ware.org'

FIWARE_PROVIDER_ROLE = 'ST Provider'
FIWARE_CUSTOMER_ROLE = 'ST Customer'
FIWARE_DEVELOPER_ROLE = 'ST Developer'

SOCIAL_AUTH_ENABLED_BACKENDS = ('fiware',)

MARKETPLACE_USER = 'store_conwet'
MARKETPLACE_PASSWORD = 'store_conwet'

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'

# Daily job that checks pending pay-per-use charges
CRONJOBS = [
    ('0 5 * * *', 'django.core.management.call_command', ['resolve_use_charging']),
]

# Hack to ignore `site` instance creation
# This will prevent site creation on syncdb
from django.db.models import signals
from django.contrib.sites.management import create_default_site
from django.contrib.sites import models as site_app

signals.post_syncdb.disconnect(create_default_site, site_app)

CLIENTS = {
    'paypal': 'wstore.charging_engine.payment_client.paypal_client.PayPalClient',
    'fipay': 'wstore.charging_engine.payment_client.fipay_client.FiPayClient',
    None: 'wstore.charging_engine.payment_client.payment_client.PaymentClient'
}

PAYMENT_CLIENT = CLIENTS[PAYMENT_METHOD]

RESOURCE_INDEX_DIR = path.join(DATADIR, path.join('admin', 'indexes'))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
        },
        'simple': {
            'format': '%(asctime)s %(name)s %(filename)s:%(lineno)s %(levelname)s - %(message)s'
        },
    },
    'handlers': {
        'null': {
            'level':'DEBUG',
            'class':'django.utils.log.NullHandler',
        },
        'console':{
            'level':'DEBUG',
            'class':'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        'django': {
            'handlers':['null'],
            'propagate': True,
            'level':'INFO',
        },
        'wstore': {
            'handlers': ['console'],
            'propagate': True,
            'level': 'DEBUG',
        }
    }
}
