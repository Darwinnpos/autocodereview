# -*- coding: utf-8 -*-
from flask import Blueprint, request, jsonify
import logging

from ..models.user import UserConfigManager, UserConfig

bp = Blueprint('config', __name__)

# 初始化配置管理器
config_manager = UserConfigManager()
logger = logging.getLogger(__name__)


@bp.route('/config', methods=['POST'])
def create_user_config():
    """创建用户配置"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400

        # 验证必需字段
        required_fields = ['user_id', 'gitlab_url', 'access_token']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'缺少必需字段: {field}'}), 400

        # 检查用户配置是否已存在
        existing_config = config_manager.load_user_config(data['user_id'])
        if existing_config:
            return jsonify({'error': '用户配置已存在，请使用更新接口'}), 409

        # 创建用户配置
        user_config = UserConfig(
            user_id=data['user_id'],
            gitlab_url=data['gitlab_url'].rstrip('/'),
            access_token=data['access_token'],
            reviewer_name=data.get('reviewer_name', 'AutoCodeReview'),
            add_labels=data.get('add_labels', True),
            add_reviewer_signature=data.get('add_reviewer_signature', True),
            add_overall_rating=data.get('add_overall_rating', True),
            analysis_rules=data.get('analysis_rules'),
            custom_templates=data.get('custom_templates'),
            add_context=data.get('add_context'),
            notification_settings=data.get('notification_settings')
        )

        # 验证配置
        errors = config_manager.validate_config(user_config)
        if errors:
            return jsonify({'error': '配置验证失败', 'details': errors}), 400

        # 保存配置
        success = config_manager.save_user_config(user_config)
        if success:
            return jsonify({
                'success': True,
                'message': '用户配置创建成功',
                'data': {'user_id': user_config.user_id}
            }), 201
        else:
            return jsonify({'error': '保存配置失败'}), 500

    except Exception as e:
        logger.error(f"Error in create_user_config: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/config/<user_id>', methods=['GET'])
def get_user_config(user_id: str):
    """获取用户配置"""
    try:
        user_config = config_manager.load_user_config(user_id)

        if not user_config:
            return jsonify({'error': '用户配置不存在'}), 404

        # 不返回敏感信息（access_token）
        config_dict = user_config.__dict__.copy()
        config_dict['access_token'] = '***'

        return jsonify({
            'success': True,
            'data': config_dict
        }), 200

    except Exception as e:
        logger.error(f"Error in get_user_config: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/config/<user_id>', methods=['PUT'])
def update_user_config(user_id: str):
    """更新用户配置"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400

        # 检查用户配置是否存在
        existing_config = config_manager.load_user_config(user_id)
        if not existing_config:
            return jsonify({'error': '用户配置不存在'}), 404

        # 更新配置
        success = config_manager.update_user_config(user_id, data)

        if success:
            return jsonify({
                'success': True,
                'message': '用户配置更新成功'
            }), 200
        else:
            return jsonify({'error': '更新配置失败'}), 500

    except Exception as e:
        logger.error(f"Error in update_user_config: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


@bp.route('/config/<user_id>', methods=['DELETE'])
def delete_user_config(user_id: str):
    """删除用户配置"""
    try:
        success = config_manager.delete_user_config(user_id)

        if success:
            return jsonify({
                'success': True,
                'message': '用户配置删除成功'
            }), 200
        else:
            return jsonify({'error': '删除配置失败'}), 500

    except Exception as e:
        logger.error(f"Error in delete_user_config: {e}")
        return jsonify({'error': '服务器内部错误'}), 500