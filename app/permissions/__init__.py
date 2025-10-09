# -*- coding: utf-8 -*-
"""
权限管理模块

负责Agent系统的所有权限控制，确保严格的安全边界：
- 操作权限验证
- 用户授权管理
- 审计日志记录
- 安全策略执行
"""

from .manager import PermissionManager
from .policies import SecurityPolicy, OperationPolicy
from .authorizer import UserAuthorizer

__all__ = [
    'PermissionManager',
    'SecurityPolicy',
    'OperationPolicy',
    'UserAuthorizer'
]