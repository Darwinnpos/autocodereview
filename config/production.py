# -*- coding: utf-8 -*-
from .default import DefaultConfig
import os


class ProductionConfig(DefaultConfig):
    DEBUG = False
    LOG_LEVEL = 'WARNING'

    # 生产环境使用环境变量
    SECRET_KEY = os.environ.get('SECRET_KEY')
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or '/data/reviews.db'
    USER_CONFIG_DIR = os.environ.get('USER_CONFIG_DIR') or '/data/user_configs'

    # 严格的速率限制
    RATELIMIT_DEFAULT = "50 per hour"

    # 限制CORS源
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '').split(',')

    # 安全配置
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'