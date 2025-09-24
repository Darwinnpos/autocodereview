# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify, current_app, session
from typing import Dict, Any
import logging
import threading

from ..services.review_service import ReviewService
from ..models.user import UserConfigManager
from ..models.auth import AuthDatabase

bp = Blueprint('review', __name__)

# 初始化服务
config_manager = UserConfigManager()
review_service = ReviewService(config_manager)
auth_db = AuthDatabase()
logger = logging.getLogger(__name__)


def _perform_review_async(username: str, mr_url: str, review_id: int):
    """异步执行代码审查"""
    try:
        logger.info(f"Starting async review for review_id: {review_id}")
        result = review_service.perform_review(username, mr_url, review_id)

        # 检查审查结果
        if result and not result.get('success', False):
            error_msg = result.get('error', '未知错误')
            logger.error(f"Review failed for review_id {review_id}: {error_msg}")
            review_service.db.fail_review_record(review_id, error_msg)
        else:
            logger.info(f"Async review completed successfully for review_id: {review_id}")

    except Exception as e:
        logger.error(f"Error in async review {review_id}: {e}")

        # 根据错误类型提供更详细的错误信息
        error_message = str(e)
        if "AI API" in error_message or "OpenAI" in error_message or "Claude" in error_message:
            if "401" in error_message or "Unauthorized" in error_message:
                error_message = f"AI服务认证失败：API密钥无效或已过期 - {error_message}"
            elif "429" in error_message or "rate limit" in error_message.lower():
                error_message = f"AI服务请求限制：API请求过于频繁，请稍后重试 - {error_message}"
            elif "timeout" in error_message.lower():
                error_message = f"AI服务超时：API请求超时，请检查网络连接或稍后重试 - {error_message}"
            else:
                error_message = f"AI服务错误：{error_message}"
        elif "GitLab" in error_message:
            error_message = f"GitLab连接错误：{error_message}"
        else:
            error_message = f"审查执行失败：{error_message}"

        review_service.db.fail_review_record(review_id, error_message)


@bp.route('/review', methods=['POST'])
def start_review():
    """启动代码审查（异步）"""
    try:
        logger.info("=== Starting review API call ===")

        # 检查用户登录状态
        user_id = session.get('user_id')
        logger.info(f"Session user_id: {user_id}")
        if not user_id:
            return jsonify({'error': '请先登录'}), 401

        # 获取当前用户信息
        user = auth_db.get_user_by_id(user_id)
        logger.info(f"Found user: {user.username if user else 'None'}")
        if not user:
            return jsonify({'error': '用户不存在'}), 404

        data = request.get_json()
        logger.info(f"Request data: {data}")

        # 验证请求数据
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400

        mr_url = data.get('mr_url')
        if not mr_url:
            return jsonify({'error': '缺少MR URL'}), 400

        # 验证MR URL格式
        logger.info(f"Validating MR URL: {mr_url}")
        is_valid, error_msg = review_service.validate_mr_url(mr_url)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        # 创建审查记录
        logger.info("Creating review record...")
        try:
            review_id = review_service.create_review_record(user.username, mr_url)
            logger.info(f"Created review record, got review_id: {review_id}")
        except ValueError as ve:
            logger.error(f"Failed to create review record: {ve}")
            return jsonify({'error': str(ve)}), 400
        except Exception as e:
            logger.error(f"Unexpected error creating review record: {e}")
            return jsonify({'error': f'创建审查记录失败：{str(e)}'}), 500

        # 启动后台任务
        logger.info("Starting background thread...")
        thread = threading.Thread(
            target=_perform_review_async,
            args=(user.username, mr_url, review_id),
            daemon=True
        )
        thread.start()
        logger.info("Background thread started")

        # 立即返回review_id
        logger.info(f"Returning success response with review_id: {review_id}")
        return jsonify({
            'success': True,
            'message': '审查已启动',
            'review_id': review_id
        }), 200

    except Exception as e:
        logger.error(f"Error in start_review: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>', methods=['GET'])
def get_review_details(review_id: int):
    """获取审查详情"""
    try:
        details = review_service.get_review_details(review_id)

        if details is None:
            return jsonify({'error': '审查记录不存在'}), 404

        return jsonify({
            'success': True,
            'data': details
        }), 200

    except Exception as e:
        logger.error(f"Error in get_review_details: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>', methods=['DELETE'])
def delete_review(review_id: int):
    """删除审查记录"""
    try:
        success = review_service.delete_review(review_id)

        if success:
            return jsonify({
                'success': True,
                'message': '审查记录已删除'
            }), 200
        else:
            return jsonify({'error': '删除失败'}), 400

    except Exception as e:
        logger.error(f"Error in delete_review: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/reviews', methods=['GET'])
def get_reviews():
    """获取审查列表"""
    try:
        user_id = request.args.get('user_id')
        limit = min(int(request.args.get('limit', 20)), current_app.config['MAX_PAGE_SIZE'])
        offset = int(request.args.get('offset', 0))

        if user_id:
            reviews = review_service.get_user_review_history(user_id, limit, offset)
        else:
            return jsonify({'error': '缺少用户ID'}), 400

        return jsonify({
            'success': True,
            'data': {
                'reviews': reviews,
                'limit': limit,
                'offset': offset,
                'total': len(reviews)
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in get_reviews: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/reviews/search', methods=['GET'])
def search_reviews():
    """搜索审查记录"""
    try:
        query = request.args.get('q', '').strip()
        user_id = request.args.get('user_id')
        limit = min(int(request.args.get('limit', 20)), current_app.config['MAX_PAGE_SIZE'])

        if not query:
            return jsonify({'error': '搜索关键词不能为空'}), 400

        results = review_service.search_reviews(query, user_id, limit)

        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'query': query,
                'total': len(results)
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in search_reviews: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/reviews/statistics', methods=['GET'])
def get_statistics():
    """获取审查统计信息"""
    try:
        user_id = request.args.get('user_id')
        days = int(request.args.get('days', 30))

        # 限制查询范围
        days = min(days, 365)

        stats = review_service.get_review_statistics(user_id, days)

        return jsonify({
            'success': True,
            'data': stats
        }), 200

    except Exception as e:
        logger.error(f"Error in get_statistics: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/export', methods=['GET'])
def export_review(review_id: int):
    """导出审查数据"""
    try:
        export_data = review_service.export_review_data(review_id)

        if not export_data:
            return jsonify({'error': '审查记录不存在'}), 404

        return jsonify({
            'success': True,
            'data': export_data
        }), 200

    except Exception as e:
        logger.error(f"Error in export_review: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/validate-mr-url', methods=['POST'])
def validate_mr_url():
    """验证MR URL"""
    try:
        data = request.get_json()
        mr_url = data.get('mr_url', '').strip()

        if not mr_url:
            return jsonify({'error': 'MR URL不能为空'}), 400

        is_valid, error_msg = review_service.validate_mr_url(mr_url)

        return jsonify({
            'success': True,
            'data': {
                'valid': is_valid,
                'error': error_msg
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in validate_mr_url: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/test-gitlab', methods=['POST'])
def test_gitlab_connection():
    """测试GitLab连接"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': '缺少用户ID'}), 400

        user_config = config_manager.load_user_config(user_id)
        if not user_config:
            return jsonify({'error': '用户配置不存在'}), 404

        is_connected, error_msg = review_service.test_gitlab_connection(user_config)

        return jsonify({
            'success': True,
            'data': {
                'connected': is_connected,
                'error': error_msg
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in test_gitlab_connection: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/pending-comments', methods=['GET'])
def get_pending_comments(review_id: int):
    """获取待确认的评论"""
    try:
        pending_comments = review_service.get_pending_comments(review_id)

        return jsonify({
            'success': True,
            'data': {
                'review_id': review_id,
                'pending_comments': pending_comments,
                'total': len(pending_comments)
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in get_pending_comments: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/confirm-comment/<int:issue_id>', methods=['POST'])
def confirm_comment(review_id: int, issue_id: int):
    """确认单个评论"""
    try:
        success = review_service.confirm_comment(review_id, issue_id)

        if success:
            return jsonify({
                'success': True,
                'message': '评论已确认并发布到GitLab'
            }), 200
        else:
            return jsonify({'error': '确认评论失败'}), 400

    except Exception as e:
        logger.error(f"Error in confirm_comment: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/reject-comment/<int:issue_id>', methods=['POST'])
def reject_comment(review_id: int, issue_id: int):
    """拒绝单个评论"""
    try:
        success = review_service.reject_comment(issue_id)

        if success:
            return jsonify({
                'success': True,
                'message': '评论已拒绝'
            }), 200
        else:
            return jsonify({'error': '拒绝评论失败'}), 400

    except Exception as e:
        logger.error(f"Error in reject_comment: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/bulk-confirm', methods=['POST'])
def bulk_confirm_comments(review_id: int):
    """批量确认评论"""
    try:
        data = request.get_json()
        issue_ids = data.get('issue_ids', [])

        if not issue_ids:
            return jsonify({'error': '请选择要确认的评论'}), 400

        if not isinstance(issue_ids, list):
            return jsonify({'error': '评论ID列表格式错误'}), 400

        result = review_service.bulk_confirm_comments(review_id, issue_ids)

        if result['success']:
            return jsonify({
                'success': True,
                'message': f'已确认 {result["confirmed_count"]} 条评论，发布 {result["posted_count"]} 条评论到GitLab',
                'data': result
            }), 200
        else:
            return jsonify({'error': result.get('error', '批量确认失败')}), 400

    except Exception as e:
        logger.error(f"Error in bulk_confirm_comments: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/progress', methods=['GET'])
def get_review_progress(review_id: int):
    """获取审查进度"""
    try:
        progress = review_service.get_review_progress(review_id)

        if progress is None:
            return jsonify({'error': '审查记录不存在'}), 404

        return jsonify({
            'success': True,
            'data': progress
        }), 200

    except Exception as e:
        logger.error(f"Error in get_review_progress: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/review/<int:review_id>/result', methods=['GET'])
def get_review_result(review_id: int):
    """获取审查最终结果"""
    try:
        result = review_service.get_review_final_result(review_id)

        if result is None:
            return jsonify({'error': '审查记录不存在'}), 404

        return jsonify({
            'success': True,
            'data': result
        }), 200

    except Exception as e:
        logger.error(f"Error in get_review_result: {e}")
        return jsonify({'error': '服务器内部错误'}), 500