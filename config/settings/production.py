from .base import *
# pyrefly: ignore [missing-import]
import dj_database_url

DEBUG = False

ALLOWED_HOSTS = ['.royalsoftwares.co.ke']

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://\w+\.royalsoftwares\.co\.ke$",
]
CORS_ALLOWED_ORIGINS = [
    "https://fahari.royalsoftwares.co.ke",
]
CSRF_TRUSTED_ORIGINS = [
    "https://*.royalsoftwares.co.ke",
    "https://api.royalsoftwares.co.ke",
]

# Database (Production) - Typically injected via DATABASE_URL env var
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='postgres://postgres:password@localhost:5432/edutechdb'),
        conn_max_age=600,
        engine='django_tenants.postgresql_backend',
    )
}

# WhiteNoise production optimizations
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = []

# Sessions and CSRF
SESSION_COOKIE_SAMESITE = 'None'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = 'None'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False

# Redis Caching (Optional but recommended)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Robust Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'workforce.log'),
            'maxBytes': 1024 * 1024 * 10, # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'workforce': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
