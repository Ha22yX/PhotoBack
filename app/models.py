import os
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager

class User(UserMixin, db.Model):
    """管理员用户模型"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True, nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class Project(db.Model):
    """摄影项目模型"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    access_link = db.Column(db.String(64), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')
    deadline = db.Column(db.Date, nullable=True)
    client_name = db.Column(db.String(100), nullable=True)
    client_email = db.Column(db.String(120), nullable=True)
    drive_folder_id = db.Column(db.String(120), nullable=True)  # Google Drive folder ID
    
    # 关系
    photos = db.relationship('Photo', backref='project', lazy=True, cascade='all, delete-orphan')
    selections = db.relationship('Selection', back_populates='project', lazy=True, cascade='all, delete-orphan')
    
    def generate_link(self):
        """生成唯一的访问链接"""
        self.access_link = str(uuid.uuid4())[:8]
        
    def __repr__(self):
        return f'<Project {self.title}>'

class Photo(db.Model):
    """照片/视频模型"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    thumbnail_filename = db.Column(db.String(100), nullable=True)  # 缩略图文件名
    file_type = db.Column(db.String(10), nullable=False)  # image 或 video
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    drive_file_id = db.Column(db.String(120), nullable=True)  # Google Drive file ID
    
    def __repr__(self):
        return f'<Photo {self.original_filename}>'
    
    @property
    def path(self):
        """返回文件的路径"""
        from flask import current_app
        return os.path.join(current_app.config['UPLOAD_FOLDER'], self.filename)
    
    @property
    def thumbnail_path(self):
        """返回缩略图的路径"""
        from flask import current_app
        if not self.thumbnail_filename:
            return None
        return os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', self.thumbnail_filename)

class Selection(db.Model):
    """客户选择的照片记录"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=True)  # 可以为空，如果是直接下载
    submit_time = db.Column(db.DateTime, default=datetime.utcnow)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    delivery_method = db.Column(db.String(20), nullable=False, default='download')  # download, email, link
    share_key = db.Column(db.String(20), nullable=True, unique=True)  # 用于生成分享链接
    
    # 关系
    project = db.relationship('Project', back_populates='selections')
    selected_photos = db.relationship('SelectedPhoto', back_populates='selection', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Selection {self.email or "Download"}>'

class SelectedPhoto(db.Model):
    """被选中的照片模型"""
    id = db.Column(db.Integer, primary_key=True)
    selection_id = db.Column(db.Integer, db.ForeignKey('selection.id'), nullable=False)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=False)
    
    # 关系
    photo = db.relationship('Photo')
    selection = db.relationship('Selection', back_populates='selected_photos')
    
    def __repr__(self):
        return f'<SelectedPhoto {self.id}>' 