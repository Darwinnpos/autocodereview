# -*- coding: utf-8 -*-
"""
授权确认API - 提供用户授权确认的REST接口

与现有Flask应用集成，提供：
- 获取待授权请求
- 批准/拒绝授权
- 授权状态查询
- 实时状态更新
"""

from flask import Blueprint, request, jsonify, session
from typing import Dict, List, Optional
import logging

from ..permissions.manager import PermissionManager
from ..permissions.authorizer import AuthorizationStatus
from ..models.auth import User

# 创建蓝图
authorization_bp = Blueprint('authorization', __name__, url_prefix='/api/authorization')

# 全局权限管理器实例（将在应用初始化时设置）
permission_manager: Optional[PermissionManager] = None

logger = logging.getLogger(__name__)


def init_authorization_api(perm_manager: PermissionManager):
    """
    初始化授权API

    Args:
        perm_manager: 权限管理器实例
    """
    global permission_manager
    permission_manager = perm_manager
    logger.info("Authorization API initialized")


def require_authentication():
    """检查用户是否已登录"""
    if 'user_id' not in session:
        return None
    return User.get_by_id(session['user_id'])


@authorization_bp.route('/pending', methods=['GET'])
def get_pending_authorizations():
    """
    获取待处理的授权请求

    Returns:
        JSON: 待处理授权请求列表
    """
    try:
        # 检查用户认证
        user = require_authentication()
        if not user:
            return jsonify({'error': '未登录'}), 401

        if not permission_manager:
            return jsonify({'error': '权限管理器未初始化'}), 500

        # 获取用户的待处理授权请求
        pending_requests = permission_manager.get_pending_authorizations(user.id)

        # 转换为API响应格式
        requests_data = []
        for auth_request in pending_requests:
            request_data = {
                'request_id': auth_request.request_id,
                'operation_type': auth_request.operation_type.value,
                'description': auth_request.description,
                'created_at': auth_request.created_at,
                'expires_at': auth_request.expires_at,
                'required_level': auth_request.required_level.value,
                'context': {
                    'resource_path': auth_request.security_context.resource_path,
                    'target_system': auth_request.security_context.target_system
                }
            }
            requests_data.append(request_data)

        return jsonify({
            'success': True,
            'message': '获取成功',
            'data': {
                'pending_requests': requests_data,
                'count': len(requests_data)
            }
        })

    except Exception as e:
        logger.error(f"Error getting pending authorizations: {e}")
        return jsonify({'error': f'获取授权请求失败: {str(e)}'}), 500


@authorization_bp.route('/approve', methods=['POST'])
def approve_authorization():
    """
    批准授权请求

    Request Body:
        {
            "request_id": "授权请求ID"
        }

    Returns:
        JSON: 批准结果
    """
    try:
        # 检查用户认证
        user = require_authentication()
        if not user:
            return jsonify({'error': '未登录'}), 401

        if not permission_manager:
            return jsonify({'error': '权限管理器未初始化'}), 500

        # 获取请求参数
        data = request.get_json()
        if not data or 'request_id' not in data:
            return jsonify({'error': '缺少request_id参数'}), 400

        request_id = data['request_id']

        # 批准授权
        success = permission_manager.approve_authorization(request_id, user.username)

        if success:
            return jsonify({
                'success': True,
                'message': '授权已批准',
                'data': {
                    'request_id': request_id,
                    'approved_by': user.username
                }
            })
        else:
            return jsonify({'error': '批准授权失败'}), 400

    except Exception as e:
        logger.error(f"Error approving authorization: {e}")
        return jsonify({'error': f'批准授权失败: {str(e)}'}), 500


@authorization_bp.route('/deny', methods=['POST'])
def deny_authorization():
    """
    拒绝授权请求

    Request Body:
        {
            "request_id": "授权请求ID",
            "reason": "拒绝原因（可选）"
        }

    Returns:
        JSON: 拒绝结果
    """
    try:
        # 检查用户认证
        user = require_authentication()
        if not user:
            return jsonify({'error': '未登录'}), 401

        if not permission_manager:
            return jsonify({'error': '权限管理器未初始化'}), 500

        # 获取请求参数
        data = request.get_json()
        if not data or 'request_id' not in data:
            return jsonify({'error': '缺少request_id参数'}), 400

        request_id = data['request_id']
        reason = data.get('reason', '用户拒绝')

        # 拒绝授权
        success = permission_manager.deny_authorization(request_id, user.username, reason)

        if success:
            return jsonify({
                'success': True,
                'message': '授权已拒绝',
                'data': {
                    'request_id': request_id,
                    'denied_by': user.username,
                    'reason': reason
                }
            })
        else:
            return jsonify({'error': '拒绝授权失败'}), 400

    except Exception as e:
        logger.error(f"Error denying authorization: {e}")
        return jsonify({'error': f'拒绝授权失败: {str(e)}'}), 500


@authorization_bp.route('/status/<request_id>', methods=['GET'])
def get_authorization_status(request_id: str):
    """
    获取授权请求状态

    Args:
        request_id: 授权请求ID

    Returns:
        JSON: 授权状态
    """
    try:
        # 检查用户认证
        user = require_authentication()
        if not user:
            return jsonify({'error': '未登录'}), 401

        if not permission_manager:
            return jsonify({'error': '权限管理器未初始化'}), 500

        # 获取授权状态
        auth_request = permission_manager.user_authorizer.get_request_status(request_id)

        if not auth_request:
            return jsonify({'error': '授权请求不存在'}), 404

        # 检查权限（只有请求者可以查看）
        if auth_request.user_id != user.id:
            return jsonify({'error': '无权查看此授权请求'}), 403

        # 返回状态信息
        status_data = {
            'request_id': auth_request.request_id,
            'status': auth_request.status.value,
            'operation_type': auth_request.operation_type.value,
            'description': auth_request.description,
            'created_at': auth_request.created_at,
            'expires_at': auth_request.expires_at
        }

        # 如果已完成，添加完成信息
        if auth_request.status in [AuthorizationStatus.APPROVED, AuthorizationStatus.DENIED]:
            status_data.update({
                'approved_at': auth_request.approved_at,
                'approved_by': auth_request.approved_by,
                'denial_reason': auth_request.denial_reason
            })

        return jsonify({
            'success': True,
            'message': '获取状态成功',
            'data': status_data
        })

    except Exception as e:
        logger.error(f"Error getting authorization status: {e}")
        return jsonify({'error': f'获取状态失败: {str(e)}'}), 500


@authorization_bp.route('/statistics', methods=['GET'])
def get_authorization_statistics():
    """
    获取授权统计信息（仅管理员）

    Returns:
        JSON: 授权统计数据
    """
    try:
        # 检查用户认证
        user = require_authentication()
        if not user:
            return jsonify({'error': '未登录'}), 401

        # 检查管理员权限（假设User模型有is_admin字段）
        if not getattr(user, 'is_admin', False):
            return jsonify({'error': '需要管理员权限'}), 403

        if not permission_manager:
            return jsonify({'error': '权限管理器未初始化'}), 500

        # 获取统计信息
        stats = permission_manager.get_permission_statistics()

        return jsonify({
            'success': True,
            'message': '获取统计信息成功',
            'data': stats
        })

    except Exception as e:
        logger.error(f"Error getting authorization statistics: {e}")
        return jsonify({'error': f'获取统计信息失败: {str(e)}'}), 500


@authorization_bp.route('/test', methods=['GET'])
def test_authorization_api():
    """
    测试授权API是否正常工作

    Returns:
        JSON: 测试结果
    """
    try:
        user = require_authentication()
        if not user:
            return jsonify({'error': '未登录'}), 401

        test_info = {
            'api_status': 'active',
            'permission_manager_initialized': permission_manager is not None,
            'user_authenticated': True,
            'user_id': user.id,
            'timestamp': __import__('time').time()
        }

        return jsonify({
            'success': True,
            'message': '授权API测试成功',
            'data': test_info
        })

    except Exception as e:
        logger.error(f"Error in authorization API test: {e}")
        return jsonify({'error': f'API测试失败: {str(e)}'}), 500


# 创建一个便捷函数来检查是否有待处理的授权
def has_pending_authorizations(user_id: str) -> bool:
    """
    检查用户是否有待处理的授权请求

    Args:
        user_id: 用户ID

    Returns:
        bool: 是否有待处理授权
    """
    try:
        if not permission_manager:
            return False

        pending_requests = permission_manager.get_pending_authorizations(user_id)
        return len(pending_requests) > 0

    except Exception as e:
        logger.error(f"Error checking pending authorizations: {e}")
        return False