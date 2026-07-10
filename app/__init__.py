import os
from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# 初始化扩展
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'admin.login'
csrf = CSRFProtect()

def create_app(test_config=None):
    """创建并配置Flask应用"""
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    default_database_uri = 'sqlite:///' + os.path.join(app.instance_path, 'photoweb.sqlite')
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev'),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', default_database_uri),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=os.path.join(app.static_folder, 'uploads'),
        SITE_URL=os.getenv('SITE_URL', 'http://localhost:5000'),
        ADMIN_EMAIL=os.getenv('ADMIN_EMAIL', 'admin@example.com'),
        SMTP_SERVER=os.getenv('SMTP_SERVER'),
        SMTP_PORT=int(os.getenv('SMTP_PORT', '465')),
        SMTP_USERNAME=os.getenv('SMTP_USERNAME'),
        SMTP_PASSWORD=os.getenv('SMTP_PASSWORD'),
        EMAIL_DOMAIN=os.getenv('EMAIL_DOMAIN'),
        SUPPORT_EMAIL=os.getenv('SUPPORT_EMAIL', os.getenv('ADMIN_EMAIL', 'admin@example.com')),
        LOG_FOLDER=os.getenv('LOG_FOLDER', '.'),
        MAX_CONTENT_LENGTH=int(os.getenv('MAX_UPLOAD_MB', '300')) * 1024 * 1024,  # 限制请求大小为300MB
        WTF_CSRF_ENABLED=True  # 启用CSRF保护
    )

    if test_config is None:
        # 加载实例配置(如果存在)
        app.config.from_pyfile('config.py', silent=True)
    else:
        # 加载测试配置
        app.config.from_mapping(test_config)

    # 确保实例文件夹存在
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)  # 初始化CSRF保护

    # 注册蓝图
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.client import bp as client_bp
    app.register_blueprint(client_bp)

    # 主页重定向到管理员登录
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('admin.login'))
    
    # 添加Rosebeg logo路由
    @app.route('/rosebeglogo')
    def rosebeg_logo():
        return send_from_directory(os.path.join(app.static_folder, 'assets'), 'logo.png')
        
    # 添加视频文件路由处理，支持范围请求
    @app.route('/static/uploads/<path:filename>')
    def serve_video(filename):
        response = send_from_directory(os.path.join(app.static_folder, 'uploads'), filename)
        response.headers['Accept-Ranges'] = 'bytes'  # 支持范围请求
        return response

    return app 
