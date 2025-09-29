"""
版本信息API
"""
from flask import Blueprint, jsonify
from ..version import get_full_version_info

bp = Blueprint('version', __name__, url_prefix='/api')

@bp.route('/version', methods=['GET'])
def get_version():
    """获取版本信息"""
    try:
        version_info = get_full_version_info()
        return jsonify({
            'success': True,
            'data': version_info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取版本信息失败: {str(e)}'
        }), 500

@bp.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    version_info = get_full_version_info()
    return jsonify({
        'status': 'healthy',
        'version': version_info['version'],
        'service': 'AutoCodeReview'
    })