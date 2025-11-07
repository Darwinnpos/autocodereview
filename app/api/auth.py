# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, session, current_app
from flask_wtf.csrf import generate_csrf
from typing import Dict, Any
import logging
import re

from ..models.auth import AuthDatabase, User
from ..utils.rate_limiter import rate_limit

bp = Blueprint('auth', __name__)

# 初始化认证数据库
auth_db = AuthDatabase()
logger = logging.getLogger(__name__)


def validate_email(email: str) -> bool:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> tuple[bool, str]:
    """验证密码强度"""
    if len(password) < 6:
        return False, "密码至少需要6位"
    if len(password) > 128:
        return False, "密码不能超过128位"
    return True, ""


@bp.route('/csrf-token', methods=['GET'])
def get_csrf_token():
    """获取CSRF token（用于前端AJAX请求）"""
    try:
        token = generate_csrf()
        return jsonify({
            'success': True,
            'csrf_token': token
        }), 200
    except Exception as e:
        logger.error(f"Error generating CSRF token: {e}")
        return jsonify({'error': 'Failed to generate CSRF token'}), 500


def test_gitlab_connection(gitlab_url: str, access_token: str) -> tuple[bool, str]:
    """测试GitLab连接"""
    try:
        import requests
        url = f"{gitlab_url.rstrip('/')}/api/v4/user"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            return True, ""
        else:
            return False, f"GitLab连接失败: {response.status_code}"

    except Exception as e:
        return False, f"GitLab连接测试失败: {str(e)}"


@bp.route('/register', methods=['POST'])
@rate_limit('default', tokens=3)  # 注册操作消费3个令牌
def register():
    """用户注册"""
    try:
        data = request.get_json()

        # 验证请求数据 - 只需要基本信息
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'缺少必填字段: {field}'}), 400

        username = data['username'].strip()
        email = data['email'].strip().lower()
        password = data['password']

        # 验证用户名
        if len(username) < 3 or len(username) > 50:
            return jsonify({'error': '用户名长度必须在3-50字符之间'}), 400

        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            return jsonify({'error': '用户名只能包含字母、数字、下划线和横线'}), 400

        # 验证邮箱
        if not validate_email(email):
            return jsonify({'error': '邮箱格式不正确'}), 400

        # 验证密码
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # 创建用户 - 不包含GitLab和AI配置
        user_id = auth_db.create_user(username, email, password)

        if user_id is None:
            return jsonify({'error': '用户名或邮箱已存在'}), 400

        logger.info(f"New user registered: {username} (ID: {user_id})")

        return jsonify({
            'success': True,
            'message': '注册成功',
            'user_id': user_id
        }), 201

    except Exception as e:
        logger.error(f"Error in register: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/login', methods=['POST'])
@rate_limit('default', tokens=2)  # 登录操作消费2个令牌
def login():
    """用户登录"""
    try:
        data = request.get_json()

        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400

        # 用户认证
        user = auth_db.authenticate_user(username, password)
        if not user:
            return jsonify({'error': '用户名或密码错误'}), 401

        # 防止会话固定攻击：清除旧的session，强制生成新的session ID
        old_session_token = session.get('session_token')
        if old_session_token:
            # 使旧的session token失效
            auth_db.invalidate_session(old_session_token)

        # 清空旧session（Flask会生成新的session ID）
        session.clear()

        # 创建新的数据库会话
        session_token = auth_db.create_session(user.id)

        # 设置新的session数据
        session['user_id'] = user.id
        session['session_token'] = session_token
        session['role'] = user.role
        session.modified = True  # 确保Flask知道session已修改

        logger.info(f"User logged in: {username} (ID: {user.id})")

        return jsonify({
            'success': True,
            'message': '登录成功',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'reviewer_name': user.reviewer_name
            },
            'session_token': session_token
        }), 200

    except Exception as e:
        logger.error(f"Error in login: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/logout', methods=['POST'])
def logout():
    """用户登出"""
    try:
        session_token = session.get('session_token')
        if session_token:
            auth_db.invalidate_session(session_token)

        session.clear()

        return jsonify({
            'success': True,
            'message': '登出成功'
        }), 200

    except Exception as e:
        logger.error(f"Error in logout: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/profile', methods=['GET'])
def get_profile():
    """获取用户资料"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        user = auth_db.get_user_by_id(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404

        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'gitlab_url': user.gitlab_url,
                'access_token': '已设置' if user.access_token else '',  # 只显示是否已设置
                'reviewer_name': user.reviewer_name,
                'ai_api_url': user.ai_api_url,
                'ai_api_key': '已设置' if user.ai_api_key else '',  # 只显示是否已设置
                'ai_model': user.ai_model,
                'review_config': user.review_config,
                'review_severity_level': user.review_severity_level,
                'review_mode': user.review_mode,
                'created_at': user.created_at,
                'last_login': user.last_login,
                'login_count': user.login_count
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in get_profile: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/profile', methods=['PUT'])
def update_profile():
    """更新用户资料（支持部分更新）"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        data = request.get_json()

        # 只获取前端实际提供的字段，支持部分更新
        update_fields = {}

        if 'gitlab_url' in data:
            gitlab_url = data['gitlab_url'].strip()
            if gitlab_url:  # 只在有值时更新
                update_fields['gitlab_url'] = gitlab_url

        if 'access_token' in data:
            access_token = data['access_token'].strip()
            if access_token:  # 只在有值时更新
                update_fields['access_token'] = access_token

        if 'reviewer_name' in data:
            reviewer_name = data['reviewer_name'].strip()
            if reviewer_name:  # 只在有值时更新
                update_fields['reviewer_name'] = reviewer_name

        if 'ai_api_url' in data:
            ai_api_url = data['ai_api_url'].strip()
            if ai_api_url:  # 只在有值时更新
                update_fields['ai_api_url'] = ai_api_url

        if 'ai_api_key' in data:
            ai_api_key = data['ai_api_key'].strip()
            if ai_api_key:  # 只在有值时更新
                update_fields['ai_api_key'] = ai_api_key

        if 'ai_model' in data:
            ai_model = data['ai_model'].strip()
            if ai_model:  # 只在有值时更新
                update_fields['ai_model'] = ai_model

        if 'review_config' in data:
            update_fields['review_config'] = data['review_config']

        if 'review_severity_level' in data:
            severity_level = data['review_severity_level'].strip()
            if severity_level in ['strict', 'standard', 'relaxed']:
                update_fields['review_severity_level'] = severity_level
            else:
                return jsonify({'error': '无效的严重程度等级'}), 400

        if 'review_mode' in data:
            review_mode = data['review_mode'].strip()
            if review_mode in ['serial', 'parallel']:
                update_fields['review_mode'] = review_mode
            else:
                return jsonify({'error': '无效的审查模式'}), 400

        # 如果提供了GitLab配置，验证连接
        if 'gitlab_url' in update_fields and 'access_token' in update_fields:
            if update_fields['gitlab_url'] and update_fields['access_token']:
                is_connected, error_msg = test_gitlab_connection(
                    update_fields['gitlab_url'],
                    update_fields['access_token']
                )
                if not is_connected:
                    return jsonify({'error': f'GitLab配置无效: {error_msg}'}), 400

        # 使用新的部分更新方法
        success = auth_db.update_user_config_partial(user_id, update_fields)

        if success:
            return jsonify({
                'success': True,
                'message': '配置更新成功'
            }), 200
        else:
            return jsonify({'error': '更新失败'}), 400

    except Exception as e:
        logger.error(f"Error in update_profile: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/check-session', methods=['GET'])
def check_session():
    """检查会话状态"""
    try:
        session_token = session.get('session_token')
        if not session_token:
            return jsonify({'authenticated': False}), 200

        user = auth_db.get_user_by_session(session_token)
        if not user:
            session.clear()
            return jsonify({'authenticated': False}), 200

        return jsonify({
            'authenticated': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in check_session: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


# 管理员专用接口
@bp.route('/admin/users', methods=['GET'])
def get_all_users():
    """获取所有用户（管理员）"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        current_user = auth_db.get_user_by_id(user_id)
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': '权限不足'}), 403

        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))

        users = auth_db.get_all_users(limit, offset)
        total_count = auth_db.get_users_count()

        return jsonify({
            'success': True,
            'users': users,
            'total': total_count,
            'limit': limit,
            'offset': offset
        }), 200

    except Exception as e:
        logger.error(f"Error in get_all_users: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/admin/users/<int:target_user_id>/status', methods=['PUT'])
def update_user_status(target_user_id):
    """更新用户状态（管理员）"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        current_user = auth_db.get_user_by_id(user_id)
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': '权限不足'}), 403

        data = request.get_json()
        action = data.get('action')  # 'activate', 'deactivate', 'make_admin', 'make_user'

        # 检查是否是对自己进行操作
        target_user = auth_db.get_user_by_id(target_user_id)
        if not target_user:
            return jsonify({'error': '用户不存在'}), 404

        is_self_operation = (user_id == target_user_id)

        if action == 'activate':
            success = auth_db.activate_user(target_user_id)
        elif action == 'deactivate':
            # 管理员不能停用自己的账户
            if is_self_operation and current_user.role == 'admin':
                return jsonify({'error': '不能停用自己的账户'}), 403
            success = auth_db.deactivate_user(target_user_id)
            if not success:
                user = auth_db.get_user_by_id(target_user_id)
                if user and hasattr(user, 'is_default_admin') and user.is_default_admin:
                    return jsonify({'error': '默认管理员账户不能停用'}), 403
                elif user and user.role == 'admin' and user.is_active:
                    # 检查是否是最后一个活跃管理员
                    active_admin_count = auth_db.get_active_admin_count()
                    if active_admin_count <= 1:
                        return jsonify({'error': '不能停用最后一个管理员账户'}), 403
                return jsonify({'error': '停用用户失败'}), 500
        elif action == 'make_admin':
            success = auth_db.change_user_role(target_user_id, 'admin')
        elif action == 'make_user':
            # 管理员不能将自己降级为普通用户
            if is_self_operation and current_user.role == 'admin':
                return jsonify({'error': '不能将自己降级为普通用户'}), 403
            success = auth_db.change_user_role(target_user_id, 'user')
            if not success:
                user = auth_db.get_user_by_id(target_user_id)
                if user and hasattr(user, 'is_default_admin') and user.is_default_admin:
                    return jsonify({'error': '默认管理员账户不能降级为普通用户'}), 403
                elif user and user.role == 'admin' and user.is_active:
                    # 检查是否是最后一个活跃管理员
                    active_admin_count = auth_db.get_active_admin_count()
                    if active_admin_count <= 1:
                        return jsonify({'error': '不能降级最后一个管理员账户'}), 403
                return jsonify({'error': '修改用户角色失败'}), 500
        elif action == 'remove':
            # 管理员不能删除自己的账户
            if is_self_operation and current_user.role == 'admin':
                return jsonify({'error': '不能删除自己的账户'}), 403
            success = auth_db.remove_user(target_user_id)
            if not success:
                user = auth_db.get_user_by_id(target_user_id)
                if user and hasattr(user, 'is_default_admin') and user.is_default_admin:
                    return jsonify({'error': '默认管理员账户不能删除'}), 403
                elif user and user.role == 'admin' and user.is_active:
                    # 检查是否是最后一个活跃管理员
                    active_admin_count = auth_db.get_active_admin_count()
                    if active_admin_count <= 1:
                        return jsonify({'error': '不能删除最后一个管理员账户'}), 403
                return jsonify({'error': '删除用户失败'}), 500
        elif action == 'reset_password':
            # 重置用户密码
            new_password = data.get('new_password', '')
            if not new_password:
                return jsonify({'error': '请输入新密码'}), 400
            if len(new_password) < 6:
                return jsonify({'error': '密码长度至少6位'}), 400
            success = auth_db.reset_user_password(target_user_id, new_password)
        else:
            return jsonify({'error': '无效的操作'}), 400

        if success:
            return jsonify({
                'success': True,
                'message': '用户状态更新成功'
            }), 200
        else:
            return jsonify({'error': '更新失败'}), 400

    except Exception as e:
        logger.error(f"Error in update_user_status: {e}")
        return jsonify({'error': '服务器内部错误'}), 500



@bp.route('/detect-models', methods=['POST'])
def detect_models():
    """探测AI模型"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        data = request.get_json()
        ai_api_url = data.get('ai_api_url', '').strip()
        ai_api_key = data.get('ai_api_key', '').strip()
        use_saved_key = data.get('use_saved_key', False)

        if not ai_api_url:
            return jsonify({'error': 'AI API URL不能为空'}), 400

        # 如果使用保存的密钥，从数据库获取
        if use_saved_key or not ai_api_key:
            user = auth_db.get_user_by_id(user_id)
            if not user or not user.ai_api_key:
                return jsonify({'error': '未找到保存的API密钥，请重新输入'}), 400
            ai_api_key = user.ai_api_key

        if not ai_api_key:
            return jsonify({'error': 'AI API密钥不能为空'}), 400

        # 调用AI API获取模型列表
        import requests
        models_url = f"{ai_api_url.rstrip('/')}/models"
        headers = {
            'Authorization': f'Bearer {ai_api_key}',
            'Content-Type': 'application/json'
        }

        import requests
        response = requests.get(models_url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            models = data.get('data', [])

            return jsonify({
                'success': True,
                'data': {
                    'models': models,
                    'total': len(models)
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': f'API请求失败: {response.status_code} - {response.text}'
            }), 400

    except Exception as e:
        # 处理特定的requests异常
        if 'requests' in locals() or 'requests' in globals():
            if isinstance(e, requests.exceptions.Timeout):
                return jsonify({'error': '请求超时，请检查API URL'}), 400
            elif isinstance(e, requests.exceptions.ConnectionError):
                return jsonify({'error': '连接失败，请检查API URL'}), 400
        
        # 处理其他异常
        logger.error(f"Error in detect_models: {e}")
        return jsonify({'error': f'探测模型失败: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error in detect_models: {e}")
        return jsonify({'error': f'探测模型失败: {str(e)}'}), 500


@bp.route('/admin/reviews', methods=['GET'])
def get_all_reviews():
    """获取所有审查记录（管理员）"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        current_user = auth_db.get_user_by_id(user_id)
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': '权限不足'}), 403

        # 这里需要从review数据库获取所有审查记录
        from ..models.review import ReviewDatabase
        review_db = ReviewDatabase()

        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))

        # 获取所有用户的审查记录
        reviews = review_db.get_user_reviews(user_id=None, limit=limit, offset=offset)
        total_count = review_db.get_reviews_count()

        return jsonify({
            'success': True,
            'reviews': reviews,
            'total': total_count,
            'limit': limit,
            'offset': offset
        }), 200

    except Exception as e:
        logger.error(f"Error in get_all_reviews: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/admin/reviews/statistics', methods=['GET'])
def get_admin_review_statistics():
    """获取管理员审查统计信息"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        current_user = auth_db.get_user_by_id(user_id)
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': '权限不足'}), 403

        # 支持两种方式：days参数或start_date/end_date参数
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if start_date and end_date:
            # 使用自定义日期范围
            from datetime import datetime
            try:
                start_dt = datetime.fromisoformat(start_date)
                end_dt = datetime.fromisoformat(end_date)
                days = (end_dt - start_dt).days + 1
            except ValueError:
                return jsonify({'error': '日期格式无效，请使用YYYY-MM-DD格式'}), 400
        else:
            # 使用天数参数（向后兼容）
            days = int(request.args.get('days', 30))
            days = min(days, 365)  # 限制最大查询范围
            start_date = None
            end_date = None

        from ..models.review import ReviewDatabase
        review_db = ReviewDatabase()

        # 获取基础统计数据
        stats = review_db.get_review_statistics(user_id=None, days=days, start_date=start_date, end_date=end_date)

        # 获取每日趋势数据
        trend_data = review_db.get_daily_review_trend(days=days, user_id=None, start_date=start_date, end_date=end_date)

        # 合并数据
        result = {
            **stats,
            'trend_data': trend_data,
            'days': days
        }

        return jsonify({
            'success': True,
            'data': result
        }), 200

    except Exception as e:
        logger.error(f"Error in get_admin_review_statistics: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/system-status', methods=['GET'])
def system_status():
    """检查系统初始化状态"""
    try:
        # 检查是否存在管理员用户
        import sqlite3
        import os

        # 如果数据库文件不存在，视为未初始化
        if not os.path.exists(auth_db.db_path):
            return jsonify({
                'success': True,
                'initialized': False,
                'needs_setup': True
            }), 200

        conn = sqlite3.connect(auth_db.db_path)
        cursor = conn.cursor()

        # 检查users表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone()

        if not table_exists:
            conn.close()
            return jsonify({
                'success': True,
                'initialized': False,
                'needs_setup': True
            }), 200

        # 检查是否有管理员
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
        admin_count = cursor.fetchone()[0]
        conn.close()

        return jsonify({
            'success': True,
            'initialized': admin_count > 0,
            'needs_setup': admin_count == 0
        }), 200

    except Exception as e:
        logger.error(f"Error in system_status: {e}")
        # 即使出错，也返回需要设置的状态
        return jsonify({
            'success': True,
            'initialized': False,
            'needs_setup': True
        }), 200


@bp.route('/initial-setup', methods=['POST'])
@rate_limit('default', tokens=5)  # 首次设置消费5个令牌
def initial_setup():
    """首次设置管理员账户（仅在没有管理员时可用）"""
    try:
        # 检查是否已有管理员
        import sqlite3
        conn = sqlite3.connect(auth_db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
        admin_count = cursor.fetchone()[0]

        if admin_count > 0:
            conn.close()
            return jsonify({'error': '系统已初始化，无法重复设置'}), 403

        # 获取请求数据
        data = request.get_json()
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                conn.close()
                return jsonify({'error': f'缺少必填字段: {field}'}), 400

        username = data['username'].strip()
        email = data['email'].strip().lower()
        password = data['password']

        # 验证用户名
        if len(username) < 3 or len(username) > 50:
            conn.close()
            return jsonify({'error': '用户名长度必须在3-50字符之间'}), 400

        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            conn.close()
            return jsonify({'error': '用户名只能包含字母、数字、下划线和横线'}), 400

        # 验证邮箱
        if not validate_email(email):
            conn.close()
            return jsonify({'error': '邮箱格式不正确'}), 400

        # 验证密码
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            conn.close()
            return jsonify({'error': error_msg}), 400

        # 创建管理员用户
        from datetime import datetime
        password_hash = auth_db._hash_password(password)

        cursor.execute('''
            INSERT INTO users (
                username, email, password_hash, role, gitlab_url,
                access_token, reviewer_name, ai_api_url, ai_api_key, ai_model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            username, email, password_hash, 'admin',
            'https://gitlab.com', '', 'AdminReviewer',
            'https://api.openai.com/v1', '', 'gpt-3.5-turbo',
            datetime.now().isoformat()
        ))

        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Initial admin user created: {username} (ID: {user_id})")

        return jsonify({
            'success': True,
            'message': '管理员账户创建成功',
            'user_id': user_id
        }), 201

    except Exception as e:
        logger.error(f"Error in initial_setup: {e}")
        return jsonify({'error': '服务器内部错误'}), 500