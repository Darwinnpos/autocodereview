# -*- coding: utf-8 -*-
import os
import sqlite3
import hashlib
import secrets
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class User:
    """用户数据类"""
    id: int
    username: str
    email: str
    password_hash: str
    role: str  # 'user' or 'admin'
    gitlab_url: str
    access_token: str
    reviewer_name: str
    ai_api_url: str
    ai_api_key: str
    ai_model: str
    review_config: str
    is_active: bool
    created_at: str
    last_login: str
    login_count: int


class AuthDatabase:
    """用户认证数据库管理"""

    def __init__(self, db_path: str = "auth.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                gitlab_url TEXT NOT NULL,
                access_token TEXT NOT NULL,
                reviewer_name TEXT NOT NULL DEFAULT 'AutoCodeReview',
                ai_api_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
                ai_api_key TEXT NOT NULL DEFAULT '',
                ai_model TEXT NOT NULL DEFAULT 'gpt-3.5-turbo',
                review_config TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login TEXT,
                login_count INTEGER DEFAULT 0
            )
        ''')

        # 会话表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # 添加 review_config 字段（如果不存在）
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'review_config' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN review_config TEXT')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions (session_token)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id)')

        # 创建默认管理员用户（如果不存在）
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
        admin_count = cursor.fetchone()[0]

        if admin_count == 0:
            # 创建默认管理员
            admin_password = self._hash_password("admin123")
            cursor.execute('''
                INSERT INTO users (
                    username, email, password_hash, role, gitlab_url,
                    access_token, reviewer_name, ai_api_url, ai_api_key, ai_model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'admin', 'admin@autocodereview.com', admin_password, 'admin',
                'https://gitlab.com', 'your-gitlab-token', 'AdminReviewer',
                'https://api.openai.com/v1', 'your-openai-api-key', 'gpt-3.5-turbo',
                datetime.now().isoformat()
            ))

        conn.commit()
        conn.close()

    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"{salt}:{password_hash.hex()}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, stored_hash = password_hash.split(':')
            password_hash_check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return stored_hash == password_hash_check.hex()
        except ValueError:
            return False

    def create_user(self, username: str, email: str, password: str,
                   gitlab_url: str = None, access_token: str = None, reviewer_name: str = "AutoCodeReview",
                   ai_api_url: str = "https://api.openai.com/v1", ai_api_key: str = "",
                   ai_model: str = "gpt-3.5-turbo") -> Optional[int]:
        """创建新用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            password_hash = self._hash_password(password)
            cursor.execute('''
                INSERT INTO users (
                    username, email, password_hash, role, gitlab_url,
                    access_token, reviewer_name, ai_api_url, ai_api_key, ai_model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                username, email, password_hash, 'user', gitlab_url,
                access_token, reviewer_name, ai_api_url, ai_api_key, ai_model,
                datetime.now().isoformat()
            ))

            user_id = cursor.lastrowid
            conn.commit()
            return user_id

        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """用户认证"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM users
            WHERE username = ? AND is_active = 1
        ''', (username,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        user_dict = dict(row)
        if not self._verify_password(password, user_dict['password_hash']):
            conn.close()
            return None

        # 更新登录信息
        cursor.execute('''
            UPDATE users SET
                last_login = ?,
                login_count = login_count + 1
            WHERE id = ?
        ''', (datetime.now().isoformat(), user_dict['id']))

        conn.commit()
        conn.close()

        return User(**user_dict)

    def create_session(self, user_id: int, expires_hours: int = 24) -> str:
        """创建用户会话"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=expires_hours)

        cursor.execute('''
            INSERT INTO sessions (user_id, session_token, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, session_token, expires_at.isoformat(), datetime.now().isoformat()))

        conn.commit()
        conn.close()

        return session_token

    def get_user_by_session(self, session_token: str) -> Optional[User]:
        """通过会话令牌获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT u.* FROM users u
            JOIN sessions s ON u.id = s.user_id
            WHERE s.session_token = ?
                AND s.expires_at > ?
                AND u.is_active = 1
        ''', (session_token, datetime.now().isoformat()))

        row = cursor.fetchone()
        conn.close()

        if row:
            return User(**dict(row))
        return None

    def invalidate_session(self, session_token: str):
        """使会话失效"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM sessions WHERE session_token = ?', (session_token,))

        conn.commit()
        conn.close()

    def cleanup_expired_sessions(self):
        """清理过期会话"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM sessions WHERE expires_at < ?', (datetime.now().isoformat(),))

        conn.commit()
        conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE id = ? AND is_active = 1', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(**dict(row))
        return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(**dict(row))
        return None

    def update_user_config(self, user_id: int, gitlab_url: str, access_token: str, reviewer_name: str,
                          ai_api_url: str = None, ai_api_key: str = None, ai_model: str = None, review_config: str = None) -> bool:
        """更新用户配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 构建更新字段
        update_fields = ['gitlab_url = ?', 'access_token = ?', 'reviewer_name = ?']
        update_values = [gitlab_url, access_token, reviewer_name]

        if ai_api_url is not None:
            update_fields.append('ai_api_url = ?')
            update_values.append(ai_api_url)

        if ai_api_key is not None:
            update_fields.append('ai_api_key = ?')
            update_values.append(ai_api_key)

        if ai_model is not None:
            update_fields.append('ai_model = ?')
            update_values.append(ai_model)

        if review_config is not None:
            update_fields.append('review_config = ?')
            update_values.append(review_config)

        update_values.append(user_id)

        cursor.execute(f'''
            UPDATE users SET
                {', '.join(update_fields)}
            WHERE id = ?
        ''', update_values)

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def update_user_config_partial(self, user_id: int, update_fields: Dict) -> bool:
        """部分更新用户配置（只更新提供的字段）"""
        if not update_fields:
            return True  # 没有字段需要更新

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 构建更新字段
        update_clauses = []
        update_values = []

        for field, value in update_fields.items():
            update_clauses.append(f'{field} = ?')
            update_values.append(value)

        update_values.append(user_id)

        cursor.execute(f'''
            UPDATE users SET
                {', '.join(update_clauses)}
            WHERE id = ?
        ''', update_values)

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def get_all_users(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """获取所有用户（管理员功能）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, username, email, role, gitlab_url, reviewer_name,
                   is_active, created_at, last_login, login_count
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_users_count(self) -> int:
        """获取用户总数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def deactivate_user(self, user_id: int) -> bool:
        """停用用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查是否是默认管理员账户
        cursor.execute('SELECT username, email FROM users WHERE id = ?', (user_id,))
        user_info = cursor.fetchone()

        if user_info and user_info[0] == 'admin' and user_info[1] == 'admin@autocodereview.com':
            conn.close()
            return False  # 不允许停用默认管理员

        cursor.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def activate_user(self, user_id: int) -> bool:
        """激活用户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('UPDATE users SET is_active = 1 WHERE id = ?', (user_id,))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def change_user_role(self, user_id: int, new_role: str) -> bool:
        """修改用户角色"""
        if new_role not in ['user', 'admin']:
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查是否是默认管理员账户
        cursor.execute('SELECT username, email, role FROM users WHERE id = ?', (user_id,))
        user_info = cursor.fetchone()

        if user_info and user_info[0] == 'admin' and user_info[1] == 'admin@autocodereview.com':
            if new_role != 'admin':
                conn.close()
                return False  # 不允许将默认管理员降级为普通用户

        cursor.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def remove_user(self, user_id: int) -> bool:
        """移除用户（软删除或硬删除）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查是否是默认管理员账户
        cursor.execute('SELECT username, email FROM users WHERE id = ?', (user_id,))
        user_info = cursor.fetchone()
        if user_info and user_info[0] == 'admin' and user_info[1] == 'admin@autocodereview.com':
            conn.close()
            return False  # 不允许删除默认管理员

        # 删除用户记录（硬删除）
        # 注意：这里不会删除审查记录，只删除用户账户
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        success = cursor.rowcount > 0

        # 清理相关的会话记录
        cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))

        conn.commit()
        conn.close()
        return success

    def reset_user_password(self, user_id: int, new_password: str) -> bool:
        """重置用户密码"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 检查用户是否存在
            cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
            if not cursor.fetchone():
                return False

            # 生成新密码哈希
            password_hash = self._hash_password(new_password)

            # 更新密码
            cursor.execute('''
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE id = ?
            ''', (password_hash, datetime.now().isoformat(), user_id))

            success = cursor.rowcount > 0

            # 清理该用户的所有会话，强制重新登录
            if success:
                cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))

            conn.commit()
            return success

        except Exception as e:
            logger.error(f"Failed to reset password for user {user_id}: {e}")
            return False
        finally:
            conn.close()

    def get_user_statistics(self) -> Dict:
        """获取用户统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 总用户数
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
        total_users = cursor.fetchone()[0]

        # 管理员数
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin" AND is_active = 1')
        admin_count = cursor.fetchone()[0]

        # 今日活跃用户
        today = datetime.now().date().isoformat()
        cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(last_login) = ? AND is_active = 1', (today,))
        today_active = cursor.fetchone()[0]

        # 本周新注册
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute('SELECT COUNT(*) FROM users WHERE created_at > ? AND is_active = 1', (week_ago,))
        new_this_week = cursor.fetchone()[0]

        conn.close()

        return {
            'total_users': total_users,
            'admin_count': admin_count,
            'today_active': today_active,
            'new_this_week': new_this_week
        }