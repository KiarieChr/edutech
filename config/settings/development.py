from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    "127.0.0.1", "localhost", "0.0.0.0", ".localhost", 
    "10.22.200.145", "192.168.100.17", "192.168.100.33", 
    "172.17.232.8", "10.47.66.12", "10.31.125.12"
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.100.29:5173",
    "http://192.168.100.58:8000",
    "http://192.168.100.58:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS.copy()
CORS_ALLOW_ALL_ORIGINS = True
CORS_ORIGIN_ALLOW_ALL = True

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': 'edutechdb',
        'USER': 'postgres',
        'PASSWORD': '6820', # Ensure this matches local dev db
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
