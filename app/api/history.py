# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, session, render_template
from app.models.review import ReviewDatabase
from app.models.auth import AuthDatabase
from datetime import datetime, timedelta
import json

history_bp = Blueprint('history', __name__)

# 创建数据库实例
review_db = ReviewDatabase()
auth_db = AuthDatabase()


def get_user_info(user):
    """统一处理用户对象，返回(user_id, role)"""
    if hasattr(user, 'role'):
        # User对象
        return str(user.id), user.role
    elif isinstance(user, dict):
        # 字典
        return str(user.get('id', '')), user.get('role', 'user')
    else:
        # 其他类型，尝试获取属性
        user_id = str(getattr(user, 'id', 'unknown'))
        role = getattr(user, 'role', 'user')
        return user_id, role


def require_login():
    """检查用户是否已登录"""
    if 'user_id' not in session:
        return False, None

    user = auth_db.get_user_by_id(session['user_id'])
    if not user:
        return False, None

    return True, user


@history_bp.route('/history')
def history_page():
    """审核历史页面"""
    is_logged_in, user = require_login()
    if not is_logged_in:
        return render_template('login.html')

    return render_template('history.html')


@history_bp.route('/api/history/statistics')
def get_statistics():
    """获取统计数据"""
    try:
        is_logged_in, user = require_login()
        if not is_logged_in:
            return jsonify({'success': False, 'error': '请先登录'})

        # 获取查询参数
        days = request.args.get('days', type=int) or None
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # 所有用户都只能查看自己的统计（管理员使用独立的admin控制台）
        user_id, role = get_user_info(user)
        username = user.username if hasattr(user, 'username') else user.get('username', '')

        # 获取统计数据（只使用用户名格式）
        stats = review_db.get_review_statistics(
            user_id=username,
            days=days,
            start_date=start_date,
            end_date=end_date
        )

        # 获取评论发布统计
        try:
            import sqlite3
            conn = sqlite3.connect(review_db.db_path)
            cursor = conn.cursor()

            # 构建时间条件
            if start_date and end_date:
                time_condition = "r.created_at >= ? AND r.created_at <= ?"
                time_params = [start_date, end_date + 'T23:59:59']
            elif days:
                since_date = (datetime.now() - timedelta(days=days)).isoformat()
                time_condition = "r.created_at > ?"
                time_params = [since_date]
            else:
                time_condition = "1=1"
                time_params = []

            # 用户条件（只使用用户名格式）
            user_condition = "r.user_id = ?"
            user_params = [username]

            # 查询评论发布统计
            query = f"""
                SELECT SUM(r.comments_posted) as total_comments_posted
                FROM reviews r
                WHERE {user_condition} AND {time_condition}
            """
            params = user_params + time_params

            cursor.execute(query, params)
            result = cursor.fetchone()
            stats['comments_posted'] = result[0] if result[0] else 0

            conn.close()
        except Exception as e:
            print(f"Error getting comments posted stats: {e}")
            stats['comments_posted'] = 0

        return jsonify({
            'success': True,
            'data': stats
        })

    except Exception as e:
        import traceback
        print(f"Error getting statistics: {e}")
        print(f"Statistics error traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'获取统计数据失败: {str(e)}'
        })


@history_bp.route('/api/history/reviews')
def get_reviews():
    """获取审查记录列表"""
    try:
        is_logged_in, user = require_login()
        if not is_logged_in:
            return jsonify({'success': False, 'error': '请先登录'})

        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 10, type=int)
        days = request.args.get('days', type=int) or None
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        status = request.args.get('status', '')
        search = request.args.get('search', '')

        # 所有用户都只能查看自己的记录（管理员使用独立的admin控制台）
        user_id, role = get_user_info(user)
        username = user.username if hasattr(user, 'username') else user.get('username', '')

        # 构建查询条件
        conditions = []
        params = []

        # 用户条件（只使用用户名格式）
        conditions.append("user_id = ?")
        params.append(username)

        # 时间条件
        if start_date and end_date:
            conditions.append("created_at >= ? AND created_at <= ?")
            params.extend([start_date, end_date + 'T23:59:59'])
        elif days:
            since_date = (datetime.now() - timedelta(days=days)).isoformat()
            conditions.append("created_at > ?")
            params.append(since_date)

        # 状态条件
        if status:
            status_list = [s.strip() for s in status.split(',') if s.strip()]
            if status_list:
                placeholders = ','.join(['?' for _ in status_list])
                conditions.append(f"status IN ({placeholders})")
                params.extend(status_list)

        # 搜索条件
        if search:
            search_conditions = [
                "project_path LIKE ?",
                "mr_title LIKE ?",
                "mr_author LIKE ?",
                "source_branch LIKE ?",
                "target_branch LIKE ?"
            ]
            search_condition = "(" + " OR ".join(search_conditions) + ")"
            conditions.append(search_condition)
            search_param = f"%{search}%"
            params.extend([search_param] * 5)

        # 执行查询
        import sqlite3
        conn = sqlite3.connect(review_db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 构建WHERE子句
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 获取总记录数
        count_query = f"SELECT COUNT(*) FROM reviews {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # 获取分页数据
        offset = (page - 1) * limit
        data_query = f"""
            SELECT * FROM reviews {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(data_query, params + [limit, offset])
        rows = cursor.fetchall()

        conn.close()

        # 转换为字典列表
        reviews = [dict(row) for row in rows]

        return jsonify({
            'success': True,
            'data': {
                'reviews': reviews,
                'total': total,
                'page': page,
                'limit': limit,
                'total_pages': (total + limit - 1) // limit
            }
        })

    except Exception as e:
        print(f"Error getting reviews: {e}")
        return jsonify({
            'success': False,
            'error': '获取审查记录失败'
        })


@history_bp.route('/api/history/trend')
def get_trend_data():
    """获取趋势数据"""
    try:
        is_logged_in, user = require_login()
        if not is_logged_in:
            return jsonify({'success': False, 'error': '请先登录'})

        # 获取查询参数
        days = request.args.get('days', 30, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # 所有用户都只能查看自己的趋势（管理员使用独立的admin控制台）
        user_id, role = get_user_info(user)
        username = user.username if hasattr(user, 'username') else user.get('username', '')

        # 获取趋势数据（只使用用户名格式）
        trend_data = review_db.get_daily_review_trend(
            days=days,
            user_id=username,
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            'success': True,
            'data': trend_data
        })

    except Exception as e:
        print(f"Error getting trend data: {e}")
        return jsonify({
            'success': False,
            'error': '获取趋势数据失败'
        })


@history_bp.route('/api/history/review/<int:review_id>')
def get_review_detail(review_id):
    """获取单个审查详情"""
    try:
        is_logged_in, user = require_login()
        if not is_logged_in:
            return jsonify({'success': False, 'error': '请先登录'})

        # 获取审查记录
        review = review_db.get_review_record(review_id)
        if not review:
            return jsonify({'success': False, 'error': '审查记录不存在'})

        # 权限检查（所有用户只能查看自己的记录）
        user_id, role = get_user_info(user)
        username = user.username if hasattr(user, 'username') else user.get('username', '')
        if review['user_id'] != username:
            return jsonify({'success': False, 'error': '权限不足'})

        # 获取相关的问题记录
        issues = review_db.get_review_issues(review_id)
        review['issues'] = issues

        return jsonify({
            'success': True,
            'data': review
        })

    except Exception as e:
        print(f"Error getting review detail: {e}")
        return jsonify({
            'success': False,
            'error': '获取审查详情失败'
        })


@history_bp.route('/api/history/review/<int:review_id>', methods=['DELETE'])
def delete_review(review_id):
    """删除审查记录"""
    try:
        is_logged_in, user = require_login()
        if not is_logged_in:
            return jsonify({'success': False, 'error': '请先登录'})

        # 获取审查记录
        review = review_db.get_review_record(review_id)
        if not review:
            return jsonify({'success': False, 'error': '审查记录不存在'})

        # 权限检查（所有用户只能删除自己的记录）
        user_id, role = get_user_info(user)
        username = user.username if hasattr(user, 'username') else user.get('username', '')
        if review['user_id'] != username:
            return jsonify({'success': False, 'error': '权限不足'})

        # 删除记录
        review_db.delete_review_record(review_id)

        return jsonify({
            'success': True,
            'message': '审查记录已删除'
        })

    except Exception as e:
        print(f"Error deleting review: {e}")
        return jsonify({
            'success': False,
            'error': '删除审查记录失败'
        })


@history_bp.route('/api/history/export')
def export_reviews():
    """导出审查记录"""
    try:
        is_logged_in, user = require_login()
        if not is_logged_in:
            return jsonify({'success': False, 'error': '请先登录'})

        # TODO: 实现导出功能
        # 这里可以生成CSV或Excel文件

        return jsonify({
            'success': False,
            'error': '导出功能暂未实现'
        })

    except Exception as e:
        print(f"Error exporting reviews: {e}")
        return jsonify({
            'success': False,
            'error': '导出失败'
        })


# 注册错误处理器
@history_bp.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': '接口不存在'}), 404


@history_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500