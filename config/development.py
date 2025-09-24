# -*- coding: utf-8 -*-
from .default import DefaultConfig


class DevelopmentConfig(DefaultConfig):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    DATABASE_PATH = 'dev_reviews.db'
    USER_CONFIG_DIR = 'dev_user_configs'

    # 在开发环境中放宽限制
    RATELIMIT_DEFAULT = "1000 per hour"

    # 允许所有源访问
    CORS_ORIGINS = "*"