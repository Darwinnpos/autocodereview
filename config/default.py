# -*- coding: utf-8 -*-
import os


class DefaultConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'autocodereview-secret-key-2025'
    DEBUG = False
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or 'reviews.db'
    USER_CONFIG_DIR = os.environ.get('USER_CONFIG_DIR') or 'user_configs'
    LOG_LEVEL = 'INFO'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file upload

    # 分页配置
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # 速率限制
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_DEFAULT = "100 per hour"

    # CORS配置
    CORS_ORIGINS = "*"

    # GitLab配置
    GITLAB_TIMEOUT = 30  # seconds
    GITLAB_MAX_RETRIES = 3