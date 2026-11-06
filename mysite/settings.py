"""
Django settings for mysite project.

Secrets and machine-specific values are read from environment variables
(a `.env` file in the project root is loaded automatically).
See `.env.example` for the full list.
"""

import os
import warnings
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = env_bool('DJANGO_DEBUG', default=True)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set when DEBUG is False.')
    # 開発用: 起動ごとにランダムなキーを使う（再起動するとログインし直しになる）
    warnings.warn('DJANGO_SECRET_KEY is not set; using a random key for this process.')
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.ngrok-free.app'] + env_list('DJANGO_ALLOWED_HOSTS')

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://*.ngrok-free.app',
] + env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False  # JavaScript から X-CSRFToken を送るため

# ngrok などのリバースプロキシ経由で HTTPS を正しく判定する
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'word_learning',
    'video_chat',
    'conversation_analysis',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mysite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mysite.wsgi.application'
ASGI_APPLICATION = 'mysite.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}


# ---------------------------------------------------------------------------
# Database / auth
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'word_learning.CustomUser'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/video_chat/video_lesson/'
LOGOUT_REDIRECT_URL = 'login'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static / media files
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # collectstatic の出力先
_project_static = BASE_DIR / 'static'
STATICFILES_DIRS = [_project_static] if _project_static.is_dir() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 公開しないファイル（一人用レッスンの録音など）。MEDIA_URL では配信されない
PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'

# 一人用レッスンの録音の制限
SOLO_MAX_RECORDING_SECONDS = 300
SOLO_MIN_RECORDING_SECONDS = 2
SOLO_MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# 発音評価に使う音素認識モデル（Hugging Face のモデル ID。初回のみ約1.3GBをダウンロードし、以降はローカルで実行）
PRONUNCIATION_MODEL = os.getenv('PRONUNCIATION_MODEL', 'facebook/wav2vec2-lv-60-espeak-cv-ft')

# 発音分析で生成・ダウンロードする一時音声ファイルの置き場所
TEMP_AUDIO_DIR = BASE_DIR / 'temp_audio'


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 3600,
        'OPTIONS': {'MAX_ENTRIES': 1000},
    }
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'debug.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        app: {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        }
        for app in ('video_chat', 'conversation_analysis', 'word_learning', 'english_conversation')
    } | {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}


# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'


# ---------------------------------------------------------------------------
# External services
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_API_KEY_SID = os.getenv('TWILIO_API_KEY_SID')
TWILIO_API_SECRET = os.getenv('TWILIO_API_SECRET')
# Twilio のルームステータスを受け取る URL（未設定ならコールバックを登録しない）
TWILIO_STATUS_CALLBACK_URL = os.getenv('TWILIO_STATUS_CALLBACK_URL') or None
TWILIO_MEDIA_REGION = 'jp1'
TWILIO_API_RETRY_COUNT = 3
TWILIO_API_RETRY_INTERVAL = 1

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

HUGGINGFACE_MODEL_NAME = 'meta-llama/Meta-Llama-3-8B'
HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN')

# ローカル LLM (llama.cpp 用 GGUF ファイル) のパス
LLM_MODEL_PATH = os.getenv('LLM_MODEL_PATH', str(BASE_DIR / 'models' / 'Phi-3-mini-4k-instruct-q4.gguf'))
