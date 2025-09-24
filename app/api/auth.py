# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, session, current_app
from typing import Dict, Any
import logging
import re

from ..models.auth import AuthDatabase, User

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

        # 创建会话
        session_token = auth_db.create_session(user.id)

        # 设置session
        session['user_id'] = user.id
        session['session_token'] = session_token
        session['role'] = user.role

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
            update_fields['gitlab_url'] = gitlab_url if gitlab_url else None

        if 'access_token' in data:
            access_token = data['access_token'].strip()
            update_fields['access_token'] = access_token if access_token else None

        if 'reviewer_name' in data:
            reviewer_name = data['reviewer_name'].strip()
            update_fields['reviewer_name'] = reviewer_name

        if 'ai_api_url' in data:
            ai_api_url = data['ai_api_url'].strip()
            update_fields['ai_api_url'] = ai_api_url if ai_api_url else None

        if 'ai_api_key' in data:
            ai_api_key = data['ai_api_key'].strip()
            update_fields['ai_api_key'] = ai_api_key if ai_api_key else None

        if 'ai_model' in data:
            ai_model = data['ai_model'].strip()
            update_fields['ai_model'] = ai_model if ai_model else None

        if 'review_config' in data:
            update_fields['review_config'] = data['review_config']

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

        if action == 'activate':
            success = auth_db.activate_user(target_user_id)
        elif action == 'deactivate':
            success = auth_db.deactivate_user(target_user_id)
            if not success:
                # 检查是否是默认管理员
                user = auth_db.get_user_by_id(target_user_id)
                if user and user.username == 'admin' and user.email == 'admin@autocodereview.com':
                    return jsonify({'error': '默认管理员账户受保护，不能停用'}), 403
        elif action == 'make_admin':
            success = auth_db.change_user_role(target_user_id, 'admin')
        elif action == 'make_user':
            success = auth_db.change_user_role(target_user_id, 'user')
            if not success:
                # 检查是否是默认管理员
                user = auth_db.get_user_by_id(target_user_id)
                if user and user.username == 'admin' and user.email == 'admin@autocodereview.com':
                    return jsonify({'error': '默认管理员账户受保护，不能降级为普通用户'}), 403
        elif action == 'remove':
            # 检查是否是默认管理员
            user = auth_db.get_user_by_id(target_user_id)
            if user and user.username == 'admin' and user.email == 'admin@autocodereview.com':
                return jsonify({'error': '默认管理员账户受保护，不能删除'}), 403
            success = auth_db.remove_user(target_user_id)
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


@bp.route('/admin/statistics', methods=['GET'])
def get_admin_statistics():
    """获取管理员统计信息"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        current_user = auth_db.get_user_by_id(user_id)
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': '权限不足'}), 403

        stats = auth_db.get_user_statistics()

        return jsonify({
            'success': True,
            'statistics': stats
        }), 200

    except Exception as e:
        logger.error(f"Error in get_admin_statistics: {e}")
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

    except requests.exceptions.Timeout:
        return jsonify({'error': '请求超时，请检查API URL'}), 400
    except requests.exceptions.ConnectionError:
        return jsonify({'error': '连接失败，请检查API URL'}), 400
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