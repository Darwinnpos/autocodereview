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
    from app.api.config import bp as config_bp
    from app.api.auth import bp as auth_bp

    app.register_blueprint(review_bp, url_prefix='/api')
    app.register_blueprint(config_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api')

    # 初始化数据库连接池
    from app.utils.db_manager import get_auth_db_manager, get_review_db_manager
    get_auth_db_manager()  # 初始化认证数据库连接池
    get_review_db_manager()  # 初始化审查数据库连接池

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

    # 健康检查端点
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'service': 'autocodereview'}

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

    return app