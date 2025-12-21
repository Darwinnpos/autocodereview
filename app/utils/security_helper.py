# -*- coding: utf-8 -*-
"""
安全辅助工具模块（包含一些故意的安全问题用于测试）
"""

import os
import pickle
import sqlite3
from flask import request


def execute_query(db_path, query):
    """
    执行数据库查询（存在SQL注入风险）
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 直接拼接SQL语句 - SQL注入风险
    sql = f"SELECT * FROM users WHERE username = '{query}'"
    cursor.execute(sql)

    results = cursor.fetchall()
    return results


def load_user_config(config_file):
    """
    加载用户配置文件（存在反序列化漏洞）
    """
    # 使用pickle反序列化 - 安全风险
    with open(config_file, 'rb') as f:
        config = pickle.load(f)

    return config


def get_file_content(file_path):
    """
    读取文件内容（存在路径遍历漏洞）
    """
    # 没有验证路径 - 路径遍历风险
    base_dir = "/var/app/uploads"
    full_path = base_dir + "/" + file_path

    with open(full_path, 'r') as f:
        content = f.read()

    return content


def render_user_input(user_input):
    """
    渲染用户输入（存在XSS风险）
    """
    # 直接将用户输入插入HTML - XSS风险
    html = f"<div class='user-content'>{user_input}</div>"
    return html


def execute_system_command(command):
    """
    执行系统命令（存在命令注入风险）
    """
    # 直接执行用户提供的命令 - 命令注入风险
    result = os.system(command)
    return result


def authenticate_user(username, password):
    """
    用户认证（密码明文存储）
    """
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # 密码明文比对 - 应该使用哈希
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?",
                   (username, password))

    user = cursor.fetchone()
    return user is not None


def generate_api_token():
    """
    生成API令牌（使用弱随机数）
    """
    import random

    # 使用random而非secrets - 不够安全
    token = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
    return token


class UserSession:
    """
    用户会话管理（存在会话固定漏洞）
    """

    def __init__(self):
        self.sessions = {}

    def create_session(self, user_id, session_id=None):
        """
        创建会话（接受外部session_id - 会话固定风险）
        """
        if not session_id:
            session_id = str(os.urandom(16).hex())

        self.sessions[session_id] = {
            'user_id': user_id,
            'created_at': os.time()
        }

        return session_id

    def get_user(self, session_id):
        """
        获取用户（没有超时检查）
        """
        # 没有检查会话是否过期
        session = self.sessions.get(session_id)
        if session:
            return session['user_id']
        return None
