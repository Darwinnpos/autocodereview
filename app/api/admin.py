# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, session
from app.models.review import ReviewDatabase
from app.models.auth import AuthDatabase
from datetime import datetime, timedelta
import sqlite3
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

# 创建数据库实例
review_db = ReviewDatabase()
auth_db = AuthDatabase()


def require_admin():
    """检查用户是否为管理员"""
    logger.debug(f"Session content: {dict(session)}")
    if 'user_id' not in session:
        logger.debug("No user_id in session")
        return False, None

    user_id = session['user_id']
    logger.debug(f"User ID: {user_id}")
    user = auth_db.get_user_by_id(user_id)
    logger.debug(f"User info: {user}")
    if not user or user.role != 'admin':
        logger.debug(f"User does not exist or is not admin, role: {user.role if user else 'None'}")
        return False, None

    logger.debug(f"Admin verification successful: {user.username}")
    return True, user


@admin_bp.route('/api/admin/statistics')
def get_admin_statistics():
    """获取管理员统计数据"""
    try:
        is_admin, user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        # 获取用户统计
        conn = sqlite3.connect(auth_db.db_path)
        cursor = conn.cursor()

        # 总用户数
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # 本周新增用户数
        week_ago = datetime.now() - timedelta(days=7)
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at > ?", (week_ago.isoformat(),))
        new_this_week = cursor.fetchone()[0]

        # 总登录次数
        cursor.execute("SELECT SUM(login_count) FROM users")
        total_logins = cursor.fetchone()[0] or 0

        # 月度活跃用户数（根据最后登录时间）
        month_ago_date = (datetime.now() - timedelta(days=30)).date()
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(last_login) >= ?", (month_ago_date,))
        month_active = cursor.fetchone()[0]

        conn.close()

        stats_data = {
            'total_users': total_users,
            'new_this_week': new_this_week,
            'total_logins': total_logins,
            'month_active': month_active
        }

        print(f"Debug - API返回的统计数据: {stats_data}")

        return jsonify({
            'success': True,
            'statistics': stats_data
        })

    except Exception as e:
        print(f"Error getting admin statistics: {e}")
        return jsonify({
            'success': False,
            'error': '获取统计数据失败'
        }), 500


@admin_bp.route('/api/admin/users')
def get_admin_users():
    """获取用户列表"""
    try:
        is_admin, user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        limit = request.args.get('limit', 10, type=int)
        offset = request.args.get('offset', 0, type=int)

        conn = sqlite3.connect(auth_db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取总数
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]

        # 获取用户列表
        cursor.execute("""
            SELECT id, username, email, role, is_active, login_count, created_at, last_login
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        users = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({
            'success': True,
            'users': users,
            'total': total
        })

    except Exception as e:
        print(f"Error getting admin users: {e}")
        return jsonify({
            'success': False,
            'error': '获取用户列表失败'
        }), 500


@admin_bp.route('/api/admin/reviews')
def get_admin_reviews():
    """获取审查记录列表"""
    try:
        is_admin, user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        limit = request.args.get('limit', 10, type=int)
        offset = request.args.get('offset', 0, type=int)

        conn = sqlite3.connect(review_db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取总数
        cursor.execute("SELECT COUNT(*) FROM reviews")
        total = cursor.fetchone()[0]

        # 获取审查记录列表
        cursor.execute("""
            SELECT id, user_id, project_path, mr_title, mr_url, status,
                   total_files_analyzed, total_issues_found, comments_posted, created_at
            FROM reviews
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        reviews = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({
            'success': True,
            'reviews': reviews,
            'total': total
        })

    except Exception as e:
        print(f"Error getting admin reviews: {e}")
        return jsonify({
            'success': False,
            'error': '获取审查记录失败'
        }), 500


@admin_bp.route('/api/admin/reviews/statistics')
def get_review_statistics():
    """获取审查统计数据"""
    try:
        is_admin, user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            return jsonify({'success': False, 'error': '请提供开始和结束日期'}), 400

        conn = sqlite3.connect(review_db.db_path)
        cursor = conn.cursor()

        # 时间条件
        time_condition_reviews = "created_at >= ? AND created_at <= ?"
        time_condition_join = "r.created_at >= ? AND r.created_at <= ?"
        time_params = [start_date, end_date + 'T23:59:59']

        # 基本统计
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_reviews,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_reviews,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_reviews,
                SUM(total_issues_found) as total_issues
            FROM reviews
            WHERE {time_condition_reviews}
        """, time_params)

        stats = cursor.fetchone()
        total_reviews = stats[0] or 0
        completed_reviews = stats[1] or 0
        failed_reviews = stats[2] or 0
        total_issues = stats[3] or 0

        # 单独查询评论统计（从issues表获取真实数据）
        cursor.execute(f"""
            SELECT
                COUNT(CASE WHEN i.comment_status IN ('confirmed', 'posted') THEN 1 END) as total_comments,
                COUNT(DISTINCT CASE WHEN i.comment_status IN ('confirmed', 'posted') THEN i.review_id END) as reviews_with_comments
            FROM issues i
            JOIN reviews r ON i.review_id = r.id
            WHERE {time_condition_join}
        """, time_params)

        comment_stats = cursor.fetchone()
        total_comments = comment_stats[0] or 0
        reviews_with_comments = comment_stats[1] or 0

        # 计算成功率和评论率
        success_rate = (completed_reviews / total_reviews * 100) if total_reviews > 0 else 0
        comment_rate = (reviews_with_comments / total_reviews * 100) if total_reviews > 0 else 0
        avg_comments_per_review = (total_comments / total_reviews) if total_reviews > 0 else 0

        # 获取趋势数据
        cursor.execute(f"""
            SELECT
                DATE(r.created_at) as date,
                COUNT(*) as total_count,
                SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) as completed_count,
                COUNT(CASE WHEN i.comment_status IN ('confirmed', 'posted') THEN 1 END) as comments_count
            FROM reviews r
            LEFT JOIN issues i ON r.id = i.review_id
            WHERE {time_condition_join}
            GROUP BY DATE(r.created_at)
            ORDER BY date
        """, time_params)

        trend_data = []
        for row in cursor.fetchall():
            trend_data.append({
                'date': row[0],
                'total_count': row[1],
                'completed_count': row[2],
                'comments_count': row[3] or 0
            })

        conn.close()

        return jsonify({
            'success': True,
            'data': {
                'total_reviews': total_reviews,
                'completed_reviews': completed_reviews,
                'failed_reviews': failed_reviews,
                'total_issues': total_issues,
                'success_rate': round(success_rate, 1),
                'total_comments': total_comments,
                'avg_comments_per_review': round(avg_comments_per_review, 1),
                'reviews_with_comments': reviews_with_comments,
                'comment_rate': round(comment_rate, 1),
                'trend_data': trend_data
            }
        })

    except Exception as e:
        print(f"Error getting review statistics: {e}")
        return jsonify({
            'success': False,
            'error': '获取统计数据失败'
        }), 500


@admin_bp.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
def update_user_status(user_id):
    """更新用户状态"""
    try:
        is_admin, admin_user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        data = request.get_json()
        action = data.get('action')

        if not action:
            return jsonify({'success': False, 'error': '缺少操作类型'}), 400

        # 执行操作
        success = False
        message = ''

        if action == 'activate':
            success = auth_db.activate_user(user_id)
            message = '用户已激活'
        elif action == 'deactivate':
            success = auth_db.deactivate_user(user_id)
            message = '用户已停用'
        elif action == 'make_admin':
            success = auth_db.change_user_role(user_id, 'admin')
            message = '用户已设为管理员'
        elif action == 'make_user':
            success = auth_db.change_user_role(user_id, 'user')
            message = '用户已设为普通用户'
        elif action == 'remove':
            success = auth_db.remove_user(user_id)
            message = '用户已删除'
        elif action == 'reset_password':
            new_password = data.get('new_password')
            if not new_password:
                logger.error(f"Reset password failed: new_password is missing")
                return jsonify({'success': False, 'error': '缺少新密码'}), 400

            logger.info(f"Attempting to reset password for user_id: {user_id}")
            success = auth_db.reset_user_password(user_id, new_password)
            logger.info(f"Password reset result for user_id {user_id}: {success}")

            if success:
                message = '密码已重置'
            else:
                logger.error(f"Password reset failed for user_id {user_id}: auth_db.reset_user_password returned False")
                return jsonify({'success': False, 'error': '重置密码失败，用户可能不存在'}), 500
        else:
            return jsonify({'success': False, 'error': '无效的操作类型'}), 400

        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': '操作失败'}), 500

    except Exception as e:
        logger.error(f"Error updating user status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'更新用户状态失败: {str(e)}'
        }), 500


@admin_bp.route('/api/admin/config', methods=['GET'])
def get_global_config():
    """获取全局配置"""
    try:
        is_admin, user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        configs = auth_db.get_global_config()

        # 将配置转换为字典格式便于前端使用
        config_dict = {}
        if configs:
            for config in configs:
                config_dict[config['config_key']] = {
                    'value': config['config_value'],
                    'is_enabled': bool(config['is_enabled']),
                    'description': config['description']
                }

        return jsonify({
            'success': True,
            'config': config_dict
        })

    except Exception as e:
        logger.error(f"Error getting global config: {e}")
        return jsonify({
            'success': False,
            'error': '获取全局配置失败'
        }), 500


@admin_bp.route('/api/admin/config', methods=['POST'])
def update_global_config():
    """更新全局配置"""
    try:
        is_admin, user = require_admin()
        if not is_admin:
            return jsonify({'success': False, 'error': '权限不足'}), 403

        data = request.get_json()

        # 更新全局AI配置启用状态
        global_ai_enabled = data.get('global_ai_enabled', False)
        auth_db.set_global_config(
            'global_ai_enabled',
            str(global_ai_enabled),
            global_ai_enabled,
            '启用全局AI配置',
            user.id
        )

        # 如果启用了全局配置，保存AI配置信息
        if global_ai_enabled:
            ai_api_url = data.get('ai_api_url', '')
            ai_api_key = data.get('ai_api_key', '')
            ai_model = data.get('ai_model', '')

            auth_db.set_global_config(
                'global_ai_api_url',
                ai_api_url,
                True,
                '全局AI API URL',
                user.id
            )

            auth_db.set_global_config(
                'global_ai_api_key',
                ai_api_key,
                True,
                '全局AI API密钥',
                user.id
            )

            auth_db.set_global_config(
                'global_ai_model',
                ai_model,
                True,
                '全局AI模型',
                user.id
            )

        return jsonify({
            'success': True,
            'message': '全局配置已更新'
        })

    except Exception as e:
        logger.error(f"Error updating global config: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'更新全局配置失败: {str(e)}'
        }), 500


# 注册错误处理器
@admin_bp.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': '接口不存在'}), 404


@admin_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500