# -*- coding: utf-8 -*-
"""
输入验证工具模块
提供常用的输入验证函数
"""

import re
from typing import Optional


def validate_email(email: str) -> bool:
    """
    验证电子邮件地址格式

    Args:
        email: 电子邮件地址字符串

    Returns:
        bool: 如果格式有效返回True，否则返回False
    """
    # 简单的邮箱验证正则表达式
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """
    验证URL格式

    Args:
        url: URL字符串

    Returns:
        bool: 如果格式有效返回True，否则返回False
    """
    # URL验证正则表达式
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))


def validate_gitlab_token(token: str) -> bool:
    """
    验证GitLab访问令牌格式

    Args:
        token: GitLab访问令牌

    Returns:
        bool: 如果格式有效返回True，否则返回False
    """
    if not token:
        return False

    # GitLab token通常以glpat-开头（Personal Access Token）
    # 或者glsa-开头（Service Account Token）
    if token.startswith('glpat-') or token.startswith('glsa-'):
        return len(token) > 20

    # 也可能是旧格式的token（纯字符串）
    return len(token) >= 20


def sanitize_input(input_str: str, max_length: Optional[int] = None) -> str:
    """
    清理用户输入，移除潜在的危险字符

    Args:
        input_str: 输入字符串
        max_length: 最大长度限制

    Returns:
        str: 清理后的字符串
    """
    if not input_str:
        return ""

    # 移除首尾空白
    cleaned = input_str.strip()

    # 如果指定了最大长度，进行截断
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]

    return cleaned


def validate_username(username: str) -> tuple[bool, Optional[str]]:
    """
    验证用户名格式

    Args:
        username: 用户名字符串

    Returns:
        tuple: (是否有效, 错误消息)
    """
    if not username:
        return False, "用户名不能为空"

    if len(username) < 3:
        return False, "用户名长度至少为3个字符"

    if len(username) > 20:
        return False, "用户名长度不能超过20个字符"

    # 只允许字母、数字和下划线
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含字母、数字和下划线"

    return True, None


def validate_password(password: str) -> tuple[bool, Optional[str]]:
    """
    验证密码强度

    Args:
        password: 密码字符串

    Returns:
        tuple: (是否有效, 错误消息)
    """
    if not password:
        return False, "密码不能为空"

    if len(password) < 6:
        return False, "密码长度至少为6个字符"

    if len(password) > 100:
        return False, "密码长度不能超过100个字符"

    return True, None
