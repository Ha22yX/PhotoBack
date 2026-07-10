import os
import uuid
import shutil
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, current_app, send_from_directory, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from app import db, csrf
from app.models import User, Project, Photo, Selection, SelectedPhoto
from app.admin import bp
from app.admin.forms import LoginForm, ProjectForm
from app.utils.email_sender import send_email, send_project_files
from app.utils.image_utils import create_thumbnail, get_thumbnail_path, optimize_image
from app.utils.video2photo import video_to_thumbnail
import glob
import traceback

def allowed_file(filename):
    """检查文件是否是允许的类型"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """管理员登录"""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('admin.login'))
        
        login_user(user, remember=form.remember_me.data)
        return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/login.html', title='Sign In', form=form)

@bp.route('/logout')
def logout():
    """管理员登出"""
    logout_user()
    return redirect(url_for('admin.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    """管理员仪表盘"""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('admin/dashboard.html', title='Dashboard', projects=projects)

@bp.route('/project/new', methods=['GET', 'POST'])
@login_required
def create_project():
    """创建新的摄影项目"""
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project(
            title=form.title.data,
            description=form.description.data,
            client_name=form.client_name.data,
            client_email=form.client_email.data
        )
        
        if form.deadline.data:
            project.deadline = form.deadline.data
            
        project.generate_link()
        db.session.add(project)
        db.session.commit()
        
        # 同步到Google Drive
        try:
            from app.admin.drive_sync import get_drive_sync
            drive_sync = get_drive_sync()
            folder_id = drive_sync.sync_project_creation(project)
            if folder_id:
                flash('Project created and synced to Google Drive successfully!', 'success')
            else:
                flash('Project created successfully, but Google Drive sync failed.', 'warning')
        except Exception as e:
            current_app.logger.error(f"Error syncing project to Google Drive: {str(e)}")
            flash('Project created, but Google Drive sync failed.', 'warning')
        
        return redirect(url_for('admin.project', project_id=project.id))
    
    return render_template('admin/create_project.html', title='Create Project', form=form)

@bp.route('/project/<int:project_id>')
@login_required
def project(project_id):
    """查看项目详情"""
    project = Project.query.get_or_404(project_id)
    return render_template('admin/project.html', title=project.title, project=project)

@bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    """编辑项目"""
    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)
    
    if form.validate_on_submit():
        form.populate_obj(project)
        db.session.commit()
        flash('Project updated successfully!', 'success')
        return redirect(url_for('admin.project', project_id=project.id))
    
    return render_template('admin/edit_project.html', title='Edit Project', form=form)

@bp.route('/project/<int:project_id>/upload', methods=['POST'])
@login_required
@csrf.exempt  # 对文件上传API禁用CSRF保护，因为我们会通过XHR请求单独处理
def upload_photos(project_id):
    """上传照片/视频到项目"""
    project = Project.query.get_or_404(project_id)
    
    if 'files[]' not in request.files:
        return jsonify({
            'success': False,
            'message': 'No file part in the request',
            'status': 400
        }), 400
    
    files = request.files.getlist('files[]')
    
    if len(files) == 0 or files[0].filename == '':
        return jsonify({
            'success': False,
            'message': 'No file selected',
            'status': 400
        }), 400
    
    # 用于跟踪创建的临时文件，确保在出错时能够清理
    temp_files = []
    # 跟踪创建的Photo实例
    created_photos = []
    
    try:
        results = []
        for file in files:
            if file.filename == '':
                continue
            
            if file and allowed_file(file.filename):
                # 安全处理文件名并生成唯一文件名
                original_filename = secure_filename(file.filename)
                file_extension = original_filename.rsplit('.', 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{file_extension}"
                
                # 确定文件类型
                file_type = 'image' if file_extension in ['png', 'jpg', 'jpeg', 'gif'] else 'video'
                
                # 临时保存原始文件
                temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp_' + filename)
                file.save(temp_path)
                temp_files.append(temp_path)  # 添加到临时文件列表
                
                # 最终文件路径
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                
                # 对图片进行优化
                if file_type == 'image':
                    try:
                        # 使用优化函数处理图片
                        compression_ratio = optimize_image(
                            input_path=temp_path, 
                            output_path=file_path, 
                            target_size_mb=10,  # 目标大小为10MB
                            preserve_size=False,  # 允许调整超大图片尺寸
                            quality=95  # 使用较高的质量值
                        )
                        
                        # 如果压缩失败，使用原始文件
                        if compression_ratio <= 0 and not os.path.exists(file_path):
                            if os.path.exists(temp_path):
                                shutil.move(temp_path, file_path)
                                temp_files.remove(temp_path)  # 从临时文件列表中移除
                        # 记录压缩信息
                        if compression_ratio > 0:
                            current_app.logger.info(f"图片 {original_filename} 已压缩 {compression_ratio:.2f}%")
                    except Exception as e:
                        current_app.logger.error(f"压缩图片 {original_filename} 失败: {str(e)}")
                        # 使用原始文件
                        if os.path.exists(temp_path):
                            shutil.move(temp_path, file_path)
                            temp_files.remove(temp_path)  # 从临时文件列表中移除
                        
                    # 为图片创建缩略图
                    thumbnail_filename = get_thumbnail_path(filename)
                    thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', thumbnail_filename)
                    create_thumbnail(file_path, thumbnail_path)
                else:
                    # 视频文件处理
                    # 先移动视频文件到最终路径
                    shutil.move(temp_path, file_path)
                    temp_files.remove(temp_path)  # 从临时文件列表中移除
                    
                    # 为视频生成首帧缩略图
                    try:
                        # 使用与图片相同的命名规则
                        thumbnail_filename = get_thumbnail_path(filename)
                        thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', thumbnail_filename)
                        
                        # 确保thumbnails目录存在
                        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                        
                        # 调用视频首帧提取函数
                        result = video_to_thumbnail(file_path, thumbnail_path)
                        
                        # 无论函数返回什么，都检查文件是否存在
                        if not os.path.exists(thumbnail_path) or os.path.getsize(thumbnail_path) == 0:
                            current_app.logger.warning(f"为视频 {original_filename} 生成缩略图失败，将尝试备用方法")
                            # 尝试使用默认方法生成
                            try:
                                import subprocess
                                # 使用ffmpeg生成缩略图 (如果安装了ffmpeg)
                                ffmpeg_cmd = f'ffmpeg -i "{file_path}" -vframes 1 -an -s 800x450 -ss 0 "{thumbnail_path}"'
                                subprocess.call(ffmpeg_cmd, shell=True)
                                if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                                    current_app.logger.info(f"使用ffmpeg为视频 {original_filename} 生成缩略图成功")
                                else:
                                    current_app.logger.error(f"备用方法也失败，将使用默认占位符")
                                    thumbnail_filename = None
                            except Exception as ffmpeg_error:
                                current_app.logger.error(f"ffmpeg处理失败: {str(ffmpeg_error)}")
                                thumbnail_filename = None
                        else:
                            current_app.logger.info(f"为视频 {original_filename} 生成缩略图成功: {thumbnail_path}")
                    except Exception as e:
                        current_app.logger.error(f"处理视频缩略图时出错: {str(e)}")
                        # 即使出错，也检查文件是否存在
                        if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                            current_app.logger.info(f"尽管有错误，缩略图文件已存在: {thumbnail_path}")
                        else:
                            thumbnail_filename = None
                
                # 创建数据库记录
                photo = Photo(
                    filename=filename,
                    original_filename=original_filename,
                    thumbnail_filename=thumbnail_filename,
                    file_type=file_type,
                    project_id=project.id
                )
                db.session.add(photo)
                db.session.flush()  # 获取ID但不提交
                
                # 跟踪创建的照片
                created_photos.append(photo)
                
                # 添加到结果
                results.append({
                    'id': photo.id,
                    'original_filename': original_filename,
                    'success': True
                })
            else:
                # 不支持的文件类型
                results.append({
                    'original_filename': file.filename,
                    'success': False,
                    'error': 'Unsupported file type'
                })
        
        # 确保清理所有剩余的临时文件
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    current_app.logger.debug(f"清理临时文件: {temp_file}")
                except Exception as e:
                    current_app.logger.warning(f"清理临时文件失败: {temp_file}, 错误: {str(e)}")
        
        # 提交所有更改到数据库
        db.session.commit()
        
        # 同步到Google Drive
        try:
            from app.admin.drive_sync import get_drive_sync
            drive_sync = get_drive_sync()
            
            # 对每张照片进行同步
            for photo in created_photos:
                drive_sync.sync_photo_upload(photo)
                
            # 如果是AJAX请求，添加同步信息到响应
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True, 
                    'message': 'Files uploaded successfully and synced to Google Drive',
                    'results': results
                })
            
            # 否则重定向到项目页面
            flash('Files uploaded successfully and synced to Google Drive!', 'success')
            return redirect(url_for('admin.project', project_id=project.id))
            
        except Exception as e:
            current_app.logger.error(f"Error syncing photos to Google Drive: {str(e)}")
            
            # 如果是AJAX请求，添加同步警告到响应
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True, 
                    'message': 'Files uploaded successfully, but Google Drive sync failed',
                    'warning': str(e),
                    'results': results
                })
            
            # 否则重定向到项目页面
            flash('Files uploaded successfully, but Google Drive sync failed.', 'warning')
            return redirect(url_for('admin.project', project_id=project.id))
        
    except Exception as e:
        # 回滚任何数据库更改
        db.session.rollback()
        current_app.logger.error(f"上传文件时出错: {str(e)}")
        
        # 清理所有临时文件
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    current_app.logger.debug(f"清理临时文件: {temp_file}")
                except Exception as clean_error:
                    current_app.logger.warning(f"清理临时文件失败: {temp_file}, 错误: {str(clean_error)}")
        
        # 如果是AJAX请求，返回错误
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Error uploading files',
                'error': str(e)
            }), 500
        
        # 否则重定向到项目页面
        flash(f'Error uploading files: {str(e)}', 'danger')
        return redirect(url_for('admin.project', project_id=project.id))

@bp.route('/project/<int:project_id>/delete')
@login_required
def delete_project(project_id):
    """删除项目"""
    project = Project.query.get_or_404(project_id)
    
    # 先尝试同步删除Google Drive项目文件夹
    try:
        from app.admin.drive_sync import get_drive_sync
        drive_sync = get_drive_sync()
        drive_sync.sync_project_deletion(project)
    except Exception as e:
        current_app.logger.error(f"Error deleting project from Google Drive: {str(e)}")
        flash('Could not sync deletion with Google Drive, but project will be deleted locally.', 'warning')
    
    # 删除项目（这会级联删除所有相关照片）
    db.session.delete(project)
    db.session.commit()
    
    flash('Project deleted successfully!', 'success')
    return redirect(url_for('admin.dashboard'))

@bp.route('/photo/<int:photo_id>/delete', methods=['POST'])
@login_required
@csrf.exempt  # 对删除照片API禁用CSRF保护，因为这是通过XHR请求处理的
def delete_photo(photo_id):
    """删除单张照片"""
    photo = Photo.query.get_or_404(photo_id)
    project_id = photo.project_id
    
    # 先尝试同步删除Google Drive照片
    drive_sync_status = False
    try:
        from app.admin.drive_sync import get_drive_sync
        drive_sync = get_drive_sync()
        drive_sync_status = drive_sync.sync_photo_deletion(photo)
    except Exception as e:
        current_app.logger.error(f"Error deleting photo from Google Drive: {str(e)}")
    
    try:
        # 删除原图
        original_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(original_path):
            os.remove(original_path)
            current_app.logger.info(f"已删除原始文件: {photo.filename}")
        else:
            current_app.logger.warning(f"原始文件不存在: {original_path}")
        
        # 删除可能存在的临时文件
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp_' + photo.filename)
        if os.path.exists(temp_path):
            os.remove(temp_path)
            current_app.logger.debug(f"已删除临时文件: temp_{photo.filename}")
        
        # 删除缩略图
        thumbnail_deleted = False
        if photo.thumbnail_filename:
            # 完整缩略图路径
            thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', photo.thumbnail_filename)
            
            # 如果缩略图存在，删除它
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                current_app.logger.info(f"已删除缩略图: {photo.thumbnail_filename}")
                thumbnail_deleted = True
            else:
                # 可能有同名但不同扩展名的缩略图
                base_name = os.path.splitext(photo.thumbnail_filename)[0]
                for ext in ['.jpg', '.jpeg', '.png']:
                    alt_thumbnail = base_name + ext
                    alt_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', alt_thumbnail)
                    if os.path.exists(alt_path):
                        os.remove(alt_path)
                        current_app.logger.info(f"已删除替代缩略图: {alt_thumbnail}")
                        thumbnail_deleted = True
            
            if not thumbnail_deleted:
                current_app.logger.warning(f"缩略图文件未找到: {thumbnail_path}")
        
        # 删除数据库记录
        db.session.delete(photo)
        db.session.commit()
        
        if drive_sync_status:
            return jsonify({"success": True, "message": "Photo and thumbnail deleted and synced with Google Drive"})
        else:
            return jsonify({"success": True, "message": "Photo and thumbnail deleted locally, but Google Drive sync failed"})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除照片时出错: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/project/<int:project_id>/selections')
@login_required
def view_selections(project_id):
    """查看项目的访客选择"""
    project = Project.query.get_or_404(project_id)
    selections = Selection.query.filter_by(project_id=project.id).order_by(Selection.submit_time.desc()).all()
    
    return render_template('admin/selections.html', title='Selections', project=project, selections=selections)

@bp.route('/selection/<int:selection_id>')
@login_required
def view_selection(selection_id):
    """查看单个选择的详情"""
    selection = Selection.query.get_or_404(selection_id)
    
    return render_template('admin/selection_detail.html', title='Selection Detail', selection=selection)

@bp.route('/selection/<int:selection_id>/send')
@login_required
def send_selection(selection_id):
    """发送选中的作品到访客邮箱"""
    selection = Selection.query.get_or_404(selection_id)
    logger = current_app.logger
    
    # 添加一个直接显示的消息
    print(f"\n===== 开始发送选择 ID: {selection_id} 到 {selection.email} =====")
    logger.info(f"开始处理发送选择 ID: {selection_id}, 用户邮箱: {selection.email}")
    
    # 在项目根目录创建调试日志
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # 获取日志目录，如果未配置则使用当前目录
    log_folder = current_app.config.get('LOG_FOLDER', '.')
    debug_log = os.path.join(log_folder, f"selection_email_debug_{timestamp}.txt")
    with open(debug_log, "w", encoding="utf-8") as f:
        f.write(f"开始发送选择 ID: {selection_id} 到 {selection.email}\n")
        f.write(f"项目: {selection.project.title}\n")
        f.write(f"选中照片数量: {len(selection.selected_photos)}\n\n")
    
    # 收集要发送的文件
    files = []
    valid_files = 0
    missing_files = 0
    
    for selected_photo in selection.selected_photos:
        photo = selected_photo.photo
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        
        if not os.path.exists(file_path):
            missing_files += 1
            logger.error(f"文件不存在: {file_path}")
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"错误: 文件不存在 - {file_path}\n")
            continue
            
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.error(f"文件大小为0: {file_path}")
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"错误: 文件大小为0 - {file_path}\n")
            continue
            
        # 使用原始文件名
        original_filename = photo.original_filename
        
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"有效文件: {original_filename}, 大小: {file_size/1024:.2f} KB\n")
            
        files.append((file_path, original_filename))
        valid_files += 1
    
    with open(debug_log, "a", encoding="utf-8") as f:
        f.write(f"\n总结: 发现{valid_files}个有效文件, {missing_files}个丢失文件\n")
    
    if not files:
        logger.error("没有有效文件可供发送")
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write("错误: 没有有效文件可供发送\n")
        flash('没有有效文件可发送！', 'danger')
        return redirect(url_for('admin.view_selection', selection_id=selection.id))
    
    # 发送邮件
    try:
        logger.info(f"开始发送 '{selection.project.title}' 项目的 {len(files)} 个文件到 {selection.email}")
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"\n开始发送邮件到: {selection.email}\n")
        
        # 添加获取是否启用测试模式的请求参数
        test_mode = request.args.get('test_mode') == '1'
        if test_mode:
            logger.info("启用测试模式: 邮件将发送到管理员邮箱而非用户邮箱")
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("⚠️ 测试模式: 邮件将发送到管理员邮箱\n")
        
        result = send_project_files(
            to_email=selection.email,
            project_title=selection.project.title,
            files=files,
            test_mode=test_mode  # 传递测试模式参数
        )
        
        if result:
            success_msg = f"成功发送邮件{'(测试模式)' if test_mode else ''}"
            logger.info(success_msg)
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"✅ {success_msg}\n")
            flash(f'文件已成功发送到{"管理员邮箱(测试模式)" if test_mode else selection.email}!', 'success')
            print(f"✅ {success_msg}")
        else:
            error_msg = f"发送邮件失败"
            logger.error(error_msg)
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"❌ {error_msg}\n")
            flash('发送邮件失败. 请检查邮件设置.', 'danger')
            print(f"❌ {error_msg}")
            
    except Exception as e:
        error_msg = f"发送邮件出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"❌ {error_msg}\n")
        flash(f'发送邮件出错: {str(e)}', 'danger')
        print(f"❌ {error_msg}")
    
    with open(debug_log, "a", encoding="utf-8") as f:
        f.write("\n发送处理完成\n")
    print(f"===== 发送处理完成, 调试日志: {debug_log} =====\n")
    
    return redirect(url_for('admin.view_selection', selection_id=selection.id))

@bp.route('/test_email')
@login_required
def test_email():
    """测试邮件发送功能"""
    import logging
    logger = logging.getLogger('photoweb.test_email')
    logger.info("开始测试邮件发送功能")
    
    # 创建测试文件
    test_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], "test_file.txt")
    with open(test_file_path, "w") as f:
        f.write("这是测试文件内容")
    
    # 记录文件路径信息
    logger.info(f"测试文件路径: {test_file_path}")
    logger.info(f"文件是否存在: {os.path.exists(test_file_path)}")
    logger.info(f"文件大小: {os.path.getsize(test_file_path)}")
    
    # 测试发送邮件
    try:
        logger.info("尝试发送测试邮件...")
        result = send_email(
            to_email="kicofy@vip.qq.com",  # 使用您的邮箱
            subject="PhotoWeb - 测试邮件",
            html_body="<h1>这是一个测试邮件</h1><p>如果您收到此邮件，说明网站邮件功能正常工作。</p>",
            attachments=[(test_file_path, "测试文件.txt")]
        )
        if result:
            logger.info("测试邮件发送成功!")
            flash('测试邮件发送成功!', 'success')
        else:
            logger.error("测试邮件发送失败!")
            flash('测试邮件发送失败!', 'danger')
    except Exception as e:
        logger.error(f"发送测试邮件时出错: {str(e)}", exc_info=True)
        flash(f'发送测试邮件时出错: {str(e)}', 'danger')
    
    # 清理测试文件
    try:
        os.remove(test_file_path)
    except:
        pass
        
    return redirect(url_for('admin.dashboard'))

@bp.route('/selection/<int:selection_id>/test_send')
@login_required
def test_send_selection(selection_id):
    """测试发送选择的照片到管理员邮箱进行验证"""
    # 获取选择记录
    selection = Selection.query.get_or_404(selection_id)
    
    # 检查选择是否有照片
    if not selection.photos:
        flash('该选择没有照片可发送', 'warning')
        return redirect(url_for('admin.view_selection', selection_id=selection_id))
    
    # 创建调试日志文件名
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    # 获取日志目录，如果未配置则使用当前目录
    log_folder = current_app.config.get('LOG_FOLDER', '.')
    debug_log = os.path.join(log_folder, f'test_email_debug_{timestamp}.txt')
    
    # 初始化日志文件
    with open(debug_log, 'w', encoding='utf-8') as f:
        f.write(f"测试邮件发送日志 - 选择ID: {selection_id}, 时间: {timestamp}\n")
        f.write(f"用户: {selection.user.username if selection.user else '未知'}, 邮箱: {selection.user.email if selection.user else '未知'}\n")
        f.write(f"项目: {selection.project.title if selection.project else '未知'}\n")
        f.write(f"选择的照片数量: {len(selection.photos)}\n")
        f.write("-" * 50 + "\n")
    
    # 准备文件
    files_to_send = []
    for photo in selection.photos:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"错误: 文件不存在 - {file_path}\n")
            continue
            
        # 检查文件大小是否为0
        if os.path.getsize(file_path) == 0:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write(f"错误: 文件大小为0 - {file_path}\n")
            continue
        
        # 如果有缩略图，使用原始文件名
        original_filename = photo.original_filename or os.path.basename(photo.filename)
        
        files_to_send.append((file_path, original_filename))
        with open(debug_log, 'a', encoding='utf-8') as f:
            f.write(f"添加文件: {original_filename} ({os.path.getsize(file_path)/1024:.2f} KB)\n")
    
    # 检查是否有有效文件
    if not files_to_send:
        with open(debug_log, 'a', encoding='utf-8') as f:
            f.write("错误: 没有有效的文件可发送\n")
        flash('没有有效的文件可发送', 'danger')
        return redirect(url_for('admin.view_selection', selection_id=selection_id))
    
    # 计算总大小
    total_size = sum(os.path.getsize(path) for path, _ in files_to_send)
    with open(debug_log, 'a', encoding='utf-8') as f:
        f.write(f"总文件大小: {total_size/1024/1024:.2f} MB\n")
        
    # 检查文件总大小
    if total_size > 20 * 1024 * 1024:  # 20MB
        with open(debug_log, 'a', encoding='utf-8') as f:
            f.write(f"警告: 文件总大小超过20MB，可能会被某些邮件服务器拒绝\n")
    
    # 获取项目标题
    project_title = selection.project.title if selection.project else "未命名项目"
    user_email = selection.user.email if selection.user else current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
    
    # 发送测试邮件
    try:
        with open(debug_log, 'a', encoding='utf-8') as f:
            f.write(f"尝试发送邮件到: {user_email} (测试模式)\n")
            f.write(f"项目标题: {project_title}\n")
            f.write(f"文件数量: {len(files_to_send)}\n")
        
        # 调用发送函数，使用test_mode=True
        result = send_project_files(
            to_email=user_email,
            project_title=project_title,
            files=files_to_send,
            test_mode=True
        )
        
        if result:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write("邮件发送成功!\n")
            flash(f'测试邮件已成功发送! 日志文件: {os.path.basename(debug_log)}', 'success')
        else:
            with open(debug_log, 'a', encoding='utf-8') as f:
                f.write("邮件发送失败!\n")
            flash(f'测试邮件发送失败! 请查看日志文件: {os.path.basename(debug_log)}', 'danger')
            
    except Exception as e:
        error_msg = f"发送测试邮件时发生错误: {str(e)}"
        with open(debug_log, 'a', encoding='utf-8') as f:
            f.write(f"{error_msg}\n")
        flash(error_msg, 'danger')
    
    return redirect(url_for('admin.view_selection', selection_id=selection_id))

@bp.route('/maintenance/cleanup-files')
@login_required
def cleanup_orphaned_files():
    """清理孤立文件（数据库中不存在引用的文件）"""
    # 获取当前所有照片的文件名
    db_filenames = set()
    db_thumbnails = set()
    
    photos = Photo.query.all()
    for photo in photos:
        if photo.filename:
            db_filenames.add(photo.filename)
        if photo.thumbnail_filename:
            db_thumbnails.add(photo.thumbnail_filename)
    
    # 主图片文件夹扫描
    upload_folder = current_app.config['UPLOAD_FOLDER']
    all_files = glob.glob(os.path.join(upload_folder, '*.*'))
    # 排除非媒体文件（如.gitkeep等）
    media_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.webm']
    media_files = [f for f in all_files if os.path.splitext(f)[1].lower() in media_extensions]
    
    # 临时文件（以temp_开头）
    temp_files = [f for f in all_files if os.path.basename(f).startswith('temp_')]
    
    # 找出孤立文件（存在于磁盘但不在数据库中）
    orphaned_files = []
    for file_path in media_files:
        filename = os.path.basename(file_path)
        if filename not in db_filenames and not filename.startswith('temp_'):
            # 检查文件的修改时间，只删除超过24小时的文件
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if datetime.now() - file_modified_time > timedelta(hours=24):
                orphaned_files.append(file_path)
    
    # 缩略图文件夹扫描
    thumbnail_folder = os.path.join(upload_folder, 'thumbnails')
    all_thumbnails = glob.glob(os.path.join(thumbnail_folder, '*.*'))
    orphaned_thumbnails = []
    for thumb_path in all_thumbnails:
        thumb_filename = os.path.basename(thumb_path)
        if thumb_filename not in db_thumbnails:
            # 检查文件的修改时间，只删除超过24小时的文件
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(thumb_path))
            if datetime.now() - file_modified_time > timedelta(hours=24):
                orphaned_thumbnails.append(thumb_path)
    
    # 统计和删除
    orphaned_count = 0
    temp_count = 0
    total_size = 0
    
    # 1. 删除孤立的原始文件
    for file_path in orphaned_files:
        try:
            file_size = os.path.getsize(file_path)
            total_size += file_size
            os.remove(file_path)
            current_app.logger.info(f"已删除孤立文件: {file_path}, 大小: {file_size/1024/1024:.2f} MB")
            orphaned_count += 1
        except Exception as e:
            current_app.logger.error(f"删除孤立文件出错: {file_path}, 错误: {str(e)}")
    
    # 2. 删除孤立的缩略图
    for thumb_path in orphaned_thumbnails:
        try:
            file_size = os.path.getsize(thumb_path)
            total_size += file_size
            os.remove(thumb_path)
            current_app.logger.info(f"已删除孤立缩略图: {thumb_path}, 大小: {file_size/1024/1024:.2f} MB")
            orphaned_count += 1
        except Exception as e:
            current_app.logger.error(f"删除孤立缩略图出错: {thumb_path}, 错误: {str(e)}")
    
    # 3. 删除所有超过24小时的临时文件
    for temp_path in temp_files:
        try:
            # 检查文件的修改时间，只删除超过24小时的文件
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(temp_path))
            if datetime.now() - file_modified_time > timedelta(hours=24):
                file_size = os.path.getsize(temp_path)
                total_size += file_size
                os.remove(temp_path)
                current_app.logger.info(f"已删除临时文件: {temp_path}, 大小: {file_size/1024/1024:.2f} MB")
                temp_count += 1
        except Exception as e:
            current_app.logger.error(f"删除临时文件出错: {temp_path}, 错误: {str(e)}")
    
    # 统计结果
    flash(f'Cleanup completed! Removed {orphaned_count} orphaned files, {temp_count} temporary files, freed up {total_size/1024/1024:.2f} MB of space', 'success')
    return redirect(url_for('admin.dashboard'))

@bp.route('/project/<int:project_id>/sync_drive', methods=['POST'])
@login_required
@csrf.exempt  # 临时禁用这个路由的CSRF保护，因为我们会在前端手动处理
def sync_project_to_drive(project_id):
    """将项目同步到Google Drive"""
    project = Project.query.get_or_404(project_id)
    
    # 记录请求信息
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    content_type = request.headers.get('Content-Type')
    
    current_app.logger.info(f"开始同步项目到Google Drive: 项目ID={project_id}, 是否为AJAX请求={is_ajax}, Content-Type={content_type}")
    current_app.logger.info(f"请求数据: {request.get_data(as_text=True)}")
    
    try:
        from app.admin.drive_sync import get_drive_sync
        
        current_app.logger.info("导入DriveSync模块成功，获取drive_sync实例")
        drive_sync = get_drive_sync()
        
        current_app.logger.info("开始全量同步项目")
        folder_id, photo_count = drive_sync.full_sync_project(project)
        
        success = folder_id is not None
        current_app.logger.info(f"同步完成，成功状态={success}, 文件夹ID={folder_id}, 照片数量={photo_count}")
        
        if folder_id:
            flash(f'Project successfully synced to Google Drive! {photo_count} photos synced.', 'success')
            message = f'Project synced to Google Drive. {photo_count} photos synced.'
        else:
            flash('Failed to sync project to Google Drive.', 'danger')
            message = 'Failed to sync project to Google Drive.'
            
        # 如果是AJAX请求，返回JSON响应
        if is_ajax:
            current_app.logger.info(f"返回AJAX成功响应: {message}")
            return jsonify({
                'success': success,
                'message': message,
                'drive_folder_id': folder_id,
                'photo_count': photo_count
            })
    except RuntimeError as e:
        # 处理Google认证相关的错误
        error_message = str(e)
        current_app.logger.error(f"捕获到RuntimeError: {error_message}")
        
        if "Google Drive认证" in error_message or "token" in error_message.lower():
            error_message = "Google Drive认证失败。请确保已正确设置token.json文件并且已完成授权。"
        
        current_app.logger.error(f"Google Drive同步错误: {str(e)}")
        flash(error_message, 'danger')
        
        # 如果是AJAX请求，返回JSON错误响应
        if is_ajax:
            current_app.logger.info(f"返回AJAX错误响应(认证错误): {error_message}")
            return jsonify({
                'success': False,
                'message': error_message,
                'is_auth_error': "认证" in error_message or "token" in error_message.lower()
            }), 500
    except Exception as e:
        stack_trace = traceback.format_exc()
        current_app.logger.error(f"同步失败，捕获到异常: {str(e)}")
        current_app.logger.error(f"异常堆栈: {stack_trace}")
        
        error_message = f'Error syncing to Google Drive: {str(e)}'
        flash(error_message, 'danger')
        
        # 如果是AJAX请求，返回JSON错误响应
        if is_ajax:
            current_app.logger.info(f"返回AJAX错误响应(通用错误): {error_message}")
            return jsonify({
                'success': False,
                'message': error_message
            }), 500
    
    # 对于非AJAX请求或者上面的代码没有返回时，重定向到项目页面
    current_app.logger.info(f"完成处理，重定向到项目页面")
    return redirect(url_for('admin.project', project_id=project.id)) 