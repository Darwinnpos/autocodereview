# -*- coding: utf-8 -*-
from flask import Flask, render_template
from flask_cors import CORS
import os


def create_app(config_name='default'):
    app = Flask(__name__)

    # 加载配置
    if config_name == 'development':
        from config.development import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    elif config_name == 'production':
        from config.production import ProductionConfig
        app.config.from_object(ProductionConfig)
    else:
        from config.default import DefaultConfig
        app.config.from_object(DefaultConfig)

    # 启用CORS
    CORS(app)

    # 注册蓝图
    from app.api.review import bp as review_bp
    from app.api.auth import bp as auth_bp
    from app.api.history import history_bp
    from app.api.admin import admin_bp
    from app.api.version import bp as version_bp
    from app.api.authorization import authorization_bp

    app.register_blueprint(review_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(history_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(version_bp)
    app.register_blueprint(authorization_bp)
    # 注意：config_bp已废弃，配置功能已迁移到auth API

    # 初始化数据库连接池
    from app.utils.db_manager import get_auth_db_manager, get_review_db_manager
    get_auth_db_manager()  # 初始化认证数据库连接池
    get_review_db_manager()  # 初始化审查数据库连接池

    # 初始化权限管理系统
    from app.permissions.manager import PermissionManager
    from app.api.authorization import init_authorization_api

    # 权限管理配置
    permission_config = {
        'authorization': {
            'request_timeout': 300,  # 5分钟
            'max_pending_requests': 50
        },
        'enable_permission_caching': False,  # 生产环境可启用
        'cache_ttl': 300
    }

    # 创建全局权限管理器
    permission_manager = PermissionManager(permission_config)

    # 初始化授权API
    init_authorization_api(permission_manager)

    # 将权限管理器存储在应用上下文中，供其他模块使用
    app.permission_manager = permission_manager

    # 注册应用关闭处理
    import atexit
    from app.utils.db_manager import close_all_connections
    atexit.register(close_all_connections)

    # 注册错误处理器
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Internal server error'}, 500

    # 健康检查端点（保持向后兼容）
    @app.route('/health')
    def health_check():
        from app.version import get_full_version_info
        version_info = get_full_version_info()
        return {
            'status': 'healthy',
            'service': 'AutoCodeReview',
            'version': version_info['version']
        }

    # Web界面路由
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/config')
    def config_page():
        # 重定向到个人资料页面，因为配置功能已经合并
        from flask import redirect
        return redirect('/profile')

    @app.route('/login')
    def login_page():
        return render_template('login.html')

    @app.route('/register')
    def register_page():
        return render_template('register.html')

    @app.route('/admin')
    def admin_page():
        return render_template('admin.html')

    @app.route('/profile')
    def profile_page():
        return render_template('profile.html')

    @app.route('/guide')
    def guide_page():
        return render_template('guide.html')

    @app.route('/authorization')
    def authorization_page():
        return render_template('authorization.html')

    return app