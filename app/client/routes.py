from flask import render_template, redirect, url_for, flash, request, abort, current_app, send_from_directory, send_file
from app import db
from app.models import Project, Photo, Selection, SelectedPhoto
from app.client import bp
from app.client.forms import SelectionForm
from app.utils.image_utils import create_photos_zip
import os
import uuid
import zipfile
import time
from flask import session
from flask import after_this_request
from app.utils.file_utils import cleanup_temp_files
from datetime import datetime, timedelta

@bp.route('/view/<access_link>', methods=['GET'])
def view_project(access_link):
    """View project content"""
    # Find the project with the matching access link
    project = Project.query.filter_by(access_link=access_link).first_or_404()
    
    # Get all photos for the project
    photos = Photo.query.filter_by(project_id=project.id).all()
    
    # Process project description for sharing
    share_description = f"View and select photos from {project.title}"
    if project.description:
        # Clean up and truncate description if needed
        cleaned_description = project.description.replace('\n', ' ').strip()
        if len(cleaned_description) > 150:
            share_description = cleaned_description[:147] + "..."
        else:
            share_description = cleaned_description
    
    # For each video file, check and update thumbnail status
    for photo in photos:
        if photo.file_type == 'video':
            # Check if the thumbnail in the database exists
            thumbnail_found = False
            
            # 1. First check the thumbnail recorded in the database
            if photo.thumbnail_filename:
                thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', photo.thumbnail_filename)
                if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                    current_app.logger.info(f"视频缩略图有效: {thumbnail_path}")
                    thumbnail_found = True
                else:
                    current_app.logger.warning(f"数据库记录的缩略图文件不存在或为空: {thumbnail_path}")
            
            # 2. If not found, try using different extensions
            if not thumbnail_found and photo.thumbnail_filename:
                base_name = os.path.splitext(photo.thumbnail_filename)[0]
                for ext in ['.jpg', '.jpeg', '.png']:
                    alt_thumbnail = base_name + ext
                    alt_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', alt_thumbnail)
                    if os.path.exists(alt_path) and os.path.getsize(alt_path) > 0:
                        # Update the thumbnail filename in the database
                        photo.thumbnail_filename = alt_thumbnail
                        try:
                            db.session.commit()
                            current_app.logger.info(f"更新了缩略图文件名: {alt_thumbnail}")
                        except Exception as e:
                            db.session.rollback()
                            current_app.logger.error(f"更新缩略图文件名时出错: {str(e)}")
                        current_app.logger.info(f"找到替代缩略图: {alt_path}")
                        thumbnail_found = True
                        break
            
            # 3. If still not found, try searching for possible thumbnails based on video file name
            if not thumbnail_found:
                video_base_name = os.path.splitext(photo.filename)[0]
                possible_thumbnails = [
                    f"{video_base_name}_thumb.jpg",
                    f"{video_base_name}_thumbnail.jpg",
                    f"thumb_{video_base_name}.jpg",
                    f"{video_base_name}.jpg"
                ]
                
                thumbnails_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails')
                if os.path.exists(thumbnails_dir):
                    for thumb_name in possible_thumbnails:
                        thumb_path = os.path.join(thumbnails_dir, thumb_name)
                        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                            # Update the thumbnail filename in the database
                            photo.thumbnail_filename = thumb_name
                            try:
                                db.session.commit()
                                current_app.logger.info(f"更新了缩略图文件名: {thumb_name}")
                            except Exception as e:
                                db.session.rollback()
                                current_app.logger.error(f"更新缩略图文件名时出错: {str(e)}")
                            current_app.logger.info(f"找到匹配的缩略图: {thumb_path}")
                            thumbnail_found = True
                            break
                            
                # 4. Still not found, try looking for any file in the thumbnails directory that starts with the video UUID
                if not thumbnail_found:
                    # Extract the UUID part of the video file name
                    uuid_part = os.path.splitext(photo.filename)[0]
                    if os.path.exists(thumbnails_dir):
                        for filename in os.listdir(thumbnails_dir):
                            if filename.startswith(uuid_part) or filename.find(uuid_part) != -1:
                                thumb_path = os.path.join(thumbnails_dir, filename)
                                if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                                    # Update the thumbnail filename in the database
                                    photo.thumbnail_filename = filename
                                    try:
                                        db.session.commit()
                                        current_app.logger.info(f"更新了缩略图文件名: {filename}")
                                    except Exception as e:
                                        db.session.rollback()
                                        current_app.logger.error(f"更新缩略图文件名时出错: {str(e)}")
                                    current_app.logger.info(f"找到基于UUID的缩略图: {thumb_path}")
                                    thumbnail_found = True
                                    break

            # 5. If still not found, try generating one
            if not thumbnail_found:
                try:
                    # Get video file path
                    video_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
                    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                        # Create thumbnail filename and path
                        video_name = os.path.splitext(photo.filename)[0]
                        thumbnail_filename = f"{video_name}_thumb.jpg"
                        thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', thumbnail_filename)
                        
                        # Ensure thumbnail directory exists
                        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                        
                        # Import video_to_thumbnail function
                        from app.utils.video2photo import video_to_thumbnail
                        
                        # Generate thumbnail
                        current_app.logger.info(f"尝试为视频 {photo.original_filename} 生成缩略图...")
                        result = video_to_thumbnail(video_path, thumbnail_path)
                        
                        if result and os.path.exists(result):
                            # Update database
                            photo.thumbnail_filename = os.path.basename(result)
                            try:
                                db.session.commit()
                                current_app.logger.info(f"成功生成并更新缩略图: {result}")
                                thumbnail_found = True
                            except Exception as e:
                                db.session.rollback()
                                current_app.logger.error(f"更新缩略图记录时出错: {str(e)}")
                        else:
                            current_app.logger.warning(f"生成缩略图失败: {video_path}")
                            try:
                                # Try using ffmpeg as a fallback method
                                import subprocess
                                ffmpeg_cmd = f'ffmpeg -i "{video_path}" -vframes 1 -an -s 800x450 -ss 0 "{thumbnail_path}"'
                                subprocess.call(ffmpeg_cmd, shell=True)
                                
                                if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                                    # Update database
                                    photo.thumbnail_filename = os.path.basename(thumbnail_path)
                                    db.session.commit()
                                    current_app.logger.info(f"使用ffmpeg成功生成缩略图: {thumbnail_path}")
                                    thumbnail_found = True
                                else:
                                    current_app.logger.error(f"ffmpeg也失败了: {video_path}")
                            except Exception as e:
                                current_app.logger.error(f"ffmpeg处理出错: {str(e)}")
                    else:
                        current_app.logger.warning(f"视频文件不存在或为空: {video_path}")
                except Exception as e:
                    current_app.logger.error(f"生成视频缩略图时出错: {str(e)}")
                    db.session.rollback()
            
            # If still not found, set thumbnail to None
            if not thumbnail_found:
                photo.thumbnail_filename = None
                try:
                    db.session.commit()
                    current_app.logger.warning(f"未找到视频 {photo.filename} 的缩略图，已将数据库记录设为null")
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"更新缩略图状态失败: {str(e)}")
    
    # Return the view
    return render_template('client/view_project.html', 
                          title=project.title, 
                          project=project, 
                          photos=photos, 
                          share_description=share_description)

@bp.route('/image/<image_uuid>')
def get_image(image_uuid):
    """根据图片UUID直接返回原始图片文件"""
    # 从图片UUID获取完整文件名
    if '.' in image_uuid:
        # 如果UUID包含扩展名，直接使用
        filename = image_uuid
    else:
        # 如果UUID不包含扩展名，在数据库中查找
        # 使用UUID前缀查找匹配的照片（文件名格式为：uuid.扩展名）
        photo = Photo.query.filter(Photo.filename.startswith(image_uuid)).first_or_404()
        filename = photo.filename
    
    # 发送图片文件
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@bp.route('/view/<access_link>/selection', methods=['GET', 'POST'])
def select_photos(access_link):
    """选择喜欢的照片并提交"""
    project = Project.query.filter_by(access_link=access_link).first_or_404()
    
    # 获取用户选择的照片ID列表
    selected_ids = request.args.getlist('photo_id', type=int)
    if not selected_ids:
        flash('Please select at least one photo first.', 'warning')
        return redirect(url_for('client.view_project', access_link=access_link))
    
    # 获取选中的照片
    selected_photos = Photo.query.filter(Photo.id.in_(selected_ids)).all()
    
    form = SelectionForm()
    if form.validate_on_submit():
        # 创建新的选择记录
        selection = Selection(
            email=form.email.data if form.delivery_method.data == 'email' else None,
            project_id=project.id,
            delivery_method=form.delivery_method.data
        )
        db.session.add(selection)
        db.session.flush()  # 获取selection.id
        
        # 添加所有选中的照片
        for photo in selected_photos:
            selected_photo = SelectedPhoto(selection_id=selection.id, photo_id=photo.id)
            db.session.add(selected_photo)
        
        db.session.commit()
        
        # 根据选择的交付方式处理
        if form.delivery_method.data == 'download':
            # 重定向到下载页面
            return redirect(url_for('client.download_photos', selection_id=selection.id))
        elif form.delivery_method.data == 'link':
            # 生成分享链接
            return redirect(url_for('client.generate_share_link', selection_id=selection.id))
        elif form.delivery_method.data == 'google_drive':
            # 生成Google Drive分享链接
            return redirect(url_for('client.generate_drive_link', selection_id=selection.id))
        else:
            # 发送邮件
            try:
                current_app.logger.info(f"自动发送选择给用户: {selection.email}, 项目: {project.title}")
                
                # 准备文件列表
                files = []
                for selected_photo in selection.selected_photos:
                    photo = selected_photo.photo
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        files.append((file_path, photo.original_filename))
                
                # 导入邮件发送函数
                from app.utils.email_sender import send_project_files
                
                # 发送邮件
                if files:
                    result = send_project_files(
                        to_email=selection.email,
                        project_title=project.title,
                        files=files,
                        test_mode=False
                    )
                    
                    if result:
                        current_app.logger.info(f"已成功发送选择的照片到: {selection.email}")
                        flash('Your photos have been sent to your email!', 'success')
                    else:
                        current_app.logger.error(f"发送选择的照片到 {selection.email} 失败")
                        flash('Failed to send photos. Please try downloading instead.', 'error')
                else:
                    current_app.logger.warning(f"没有找到有效的文件可发送给: {selection.email}")
                    flash('No valid files found to send.', 'error')
                    
            except Exception as e:
                current_app.logger.error(f"发送选择时出错: {str(e)}", exc_info=True)
                flash('An error occurred while sending your photos.', 'error')
            
            return redirect(url_for('client.thank_you', access_link=access_link))
    
    return render_template('client/select_form.html', 
                          title='Submit Selection', 
                          project=project, 
                          selected_photos=selected_photos, 
                          form=form)

@bp.route('/download/<int:selection_id>')
def download_photos(selection_id):
    """下载选中的照片"""
    selection = Selection.query.get_or_404(selection_id)
    project = selection.project
    
    # 准备文件列表
    files = []
    for selected_photo in selection.selected_photos:
        photo = selected_photo.photo
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            files.append((file_path, photo.original_filename))
    
    if not files:
        flash('No valid files found for download.', 'error')
        return redirect(url_for('client.thank_you', access_link=project.access_link))
    
    # 如果只有一张图片，直接下载原图而不打包
    if len(files) == 1:
        file_path, original_filename = files[0]
        current_app.logger.info(f"用户只选择了一张图片，直接下载原图: {original_filename}")
        
        # 从会话中清除已下载的图片路径
        session.pop('image_paths', None)
        session.pop('download_file', None)
        
        return send_file(file_path, as_attachment=True, download_name=original_filename)
    
    # 创建临时ZIP文件
    temp_dir = os.path.join(current_app.static_folder, 'uploads', 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    timestamp = int(time.time())
    zip_filename = f"selected_photos_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
    
    # 压缩文件
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file_path, original_filename in files:
            # 使用原始文件名而不是系统生成的文件名
            zipf.write(file_path, original_filename)
    
    # 在发送文件前设置清理回调
    @after_this_request
    def cleanup_old_files(response):
        try:
            cleanup_temp_files(temp_dir, max_age_hours=24, file_extensions=['.zip'])
            current_app.logger.info("已清理旧的临时ZIP文件")
        except Exception as e:
            current_app.logger.error(f"清理临时文件时出错: {str(e)}")
        return response
    
    # 将ZIP文件的下载链接保存到会话中
    download_url = url_for('client.get_download_file', filename=zip_filename)
    session['download_file'] = download_url
    
    # 从会话中清除已下载的图片路径
    session.pop('image_paths', None)
    
    # 重定向到感谢页面
    return redirect(url_for('client.thank_you', access_link=project.access_link))

@bp.route('/get_download_file/<filename>')
def get_download_file(filename):
    """获取下载文件"""
    temp_dir = os.path.join(current_app.static_folder, 'uploads', 'temp')
    file_path = os.path.join(temp_dir, filename)
    
    if not os.path.exists(file_path):
        flash('Download file not found.', 'error')
        return redirect(url_for('main.index'))
    
    # 从会话中清除下载链接
    @after_this_request
    def remove_download_link(response):
        session.pop('download_file', None)
        return response
    
    return send_file(file_path, as_attachment=True, download_name=filename)

@bp.route('/view/<access_link>/thank-you')
def thank_you(access_link):
    """感谢页面"""
    project = Project.query.filter_by(access_link=access_link).first_or_404()
    
    # 获取最新的选择记录
    selection = Selection.query.filter_by(project_id=project.id).order_by(Selection.submit_time.desc()).first()
    
    # 如果是下载方式但没有下载链接，重新生成下载链接
    if selection and selection.delivery_method == 'download' and 'download_file' not in session:
        selected_photos = [sp.photo for sp in selection.selected_photos]
        if selected_photos:
            # 检查是否存在已生成的ZIP文件
            temp_dir = os.path.join(current_app.static_folder, 'uploads', 'temp')
            recent_files = []
            
            if os.path.exists(temp_dir):
                # 查找最近创建的与该选择相关的ZIP文件
                now = time.time()
                cutoff_time = now - 3600  # 1小时内的文件
                
                for filename in os.listdir(temp_dir):
                    if filename.startswith("selected_photos_") and filename.endswith(".zip"):
                        file_path = os.path.join(temp_dir, filename)
                        if os.path.isfile(file_path) and os.path.getmtime(file_path) > cutoff_time:
                            recent_files.append((filename, os.path.getmtime(file_path)))
                
                # 使用最新创建的ZIP文件
                if recent_files:
                    recent_files.sort(key=lambda x: x[1], reverse=True)
                    newest_file = recent_files[0][0]
                    session['download_file'] = url_for('client.get_download_file', filename=newest_file)
    
    return render_template('client/thank_you.html', title='Thank You', project=project, selection=selection)

@bp.route('/generate_link/<int:selection_id>')
def generate_share_link(selection_id):
    """生成并显示分享链接"""
    selection = Selection.query.get_or_404(selection_id)
    project = selection.project
    
    # 准备文件列表
    files = []
    for selected_photo in selection.selected_photos:
        photo = selected_photo.photo
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            files.append((file_path, photo.original_filename, photo.id))
    
    if not files:
        flash('No valid files found to share.', 'error')
        return redirect(url_for('client.thank_you', access_link=project.access_link))
    
    # 生成唯一的分享密钥
    share_key = uuid.uuid4().hex[:12]
    
    # 更新选择记录以包含分享密钥
    selection.share_key = share_key
    db.session.commit()
    
    # 生成分享链接 - 使用项目访问链接和选择ID
    share_link = f"{current_app.config['SITE_URL']}/view/{project.access_link}/shared/{share_key}"
    
    # 保存分享链接到会话
    session['share_link'] = share_link
    
    # 重定向到感谢页面
    return redirect(url_for('client.thank_you', access_link=project.access_link))

@bp.route('/view/<access_link>/shared/<share_key>')
def view_shared_selection(access_link, share_key):
    """查看通过分享链接共享的照片"""
    # 查找项目
    project = Project.query.filter_by(access_link=access_link).first_or_404()
    
    # 查找具有分享密钥的选择
    selection = Selection.query.filter_by(project_id=project.id, share_key=share_key).first_or_404()
    
    # 获取所选照片
    photos = []
    for selected_photo in selection.selected_photos:
        photo = selected_photo.photo
        # 检查文件是否存在并且不为空
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            photos.append(photo)
    
    return render_template('client/shared_photos.html', 
                          project=project, 
                          photos=photos,
                          selection=selection,
                          access_link=access_link,
                          share_key=share_key)

@bp.route('/view/<access_link>/shared/<share_key>/download')
def download_shared_photos(access_link, share_key):
    """下载通过分享链接共享的所有照片"""
    # 查找项目
    project = Project.query.filter_by(access_link=access_link).first_or_404()
    
    # 查找具有分享密钥的选择
    selection = Selection.query.filter_by(project_id=project.id, share_key=share_key).first_or_404()
    
    # 准备文件列表
    files = []
    for selected_photo in selection.selected_photos:
        photo = selected_photo.photo
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            files.append((file_path, photo.original_filename))
    
    if not files:
        flash('No valid files found for download.', 'error')
        return redirect(url_for('client.view_shared_selection', access_link=access_link, share_key=share_key))
    
    # 如果只有一张图片，直接下载原图而不打包
    if len(files) == 1:
        file_path, original_filename = files[0]
        current_app.logger.info(f"只有一张图片，直接下载原图: {original_filename}")
        return send_file(file_path, as_attachment=True, download_name=original_filename)
    
    # 创建临时ZIP文件
    temp_dir = os.path.join(current_app.static_folder, 'uploads', 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    timestamp = int(time.time())
    zip_filename = f"shared_photos_{timestamp}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
    
    # 压缩文件
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file_path, original_filename in files:
            # 使用原始文件名而不是系统生成的文件名
            zipf.write(file_path, original_filename)
    
    # 在发送文件前设置清理回调
    @after_this_request
    def cleanup_old_files(response):
        try:
            cleanup_temp_files(temp_dir, max_age_hours=24, file_extensions=['.zip'])
            current_app.logger.info("已清理旧的临时ZIP文件")
        except Exception as e:
            current_app.logger.error(f"清理临时文件时出错: {str(e)}")
        return response
    
    return send_file(zip_path, as_attachment=True, download_name=f"{project.title}_shared_photos.zip")

@bp.route('/generate_drive_link/<int:selection_id>')
def generate_drive_link(selection_id):
    """生成Google Drive分享链接"""
    selection = Selection.query.get_or_404(selection_id)
    project = selection.project
    
    # 确保此选择记录实际存在照片
    if not selection.selected_photos:
        flash('No photos selected to share.', 'error')
        return redirect(url_for('client.thank_you', access_link=project.access_link))
    
    try:
        current_app.logger.info(f"为选择 ID: {selection.id} 生成Google Drive分享链接")
        
        # 获取所有选中照片的Drive文件ID
        drive_file_ids = []
        photo_names = []  # 记录照片名称用于日志
        for selected_photo in selection.selected_photos:
            photo = selected_photo.photo
            if photo.drive_file_id:
                drive_file_ids.append(photo.drive_file_id)
                photo_names.append(photo.original_filename)
            else:
                current_app.logger.warning(f"照片 {photo.id} ({photo.original_filename}) 没有关联的Drive文件ID")
        
        if not drive_file_ids:
            current_app.logger.error("没有可用的Drive文件ID")
            flash('Failed to generate Google Drive link. No valid files found.', 'error')
            return redirect(url_for('client.thank_you', access_link=project.access_link))
        
        # 记录要分享的照片信息
        current_app.logger.info(f"准备分享 {len(drive_file_ids)} 张照片: {', '.join(photo_names)}")
        
        # 使用GoogleDriveManager生成分享链接
        try:
            from app.admin.drive_sync import get_drive_sync
            drive_sync = get_drive_sync()
            drive_manager = drive_sync.drive_manager
            
            # 检查项目是否有有效的Drive文件夹ID
            if not project.drive_folder_id:
                current_app.logger.warning(f"项目 {project.id} 没有Google Drive文件夹ID，尝试同步项目")
                
                # 尝试同步项目以获取文件夹ID
                project_folder_id = drive_manager.sync_project(str(project.id), project.title)
                if not project_folder_id:
                    current_app.logger.error(f"无法为项目 {project.id} 创建Google Drive文件夹")
                    flash('Failed to create Google Drive folder.', 'error')
                    return redirect(url_for('client.thank_you', access_link=project.access_link))
                    
                # 更新项目的Drive文件夹ID
                project.drive_folder_id = project_folder_id
                db.session.commit()
                current_app.logger.info(f"已更新项目的Drive文件夹ID: {project_folder_id}")
            
            # 创建合集名称 - 使用项目名称和选择ID
            collection_name = f"Selection_{selection.id}_{project.title}"
            
            # 使用create_shortcuts_collection创建快捷方式合集
            current_app.logger.info(f"为 {len(drive_file_ids)} 个文件创建快捷方式合集")
            collection_result = drive_manager.create_shortcuts_collection(drive_file_ids, collection_name)
            
            if not collection_result or 'collection_link' not in collection_result:
                current_app.logger.error("创建快捷方式合集失败")
                flash('Failed to create Google Drive collection.', 'error')
                return redirect(url_for('client.thank_you', access_link=project.access_link))
            
            # 获取合集信息
            collection_link = collection_result.get('collection_link')
            shortcuts_count = collection_result.get('shortcuts_count', 0)
            collection_name = collection_result.get('collection_name')
            collection_id = collection_result.get('collection_id')
            
            current_app.logger.info(f"成功创建快捷方式合集 '{collection_name}' (ID: {collection_id})，包含 {shortcuts_count} 个快捷方式")
            
            # 保存合集信息为JSON
            import json
            collection_data = {
                'collection_id': collection_id,
                'collection_name': collection_name,
                'collection_link': collection_link,
                'shortcuts_count': shortcuts_count
            }
            collection_json = json.dumps(collection_data)
            
            # 更新Selection记录
            selection.share_key = collection_json
            db.session.commit()
            
            # 保存合集链接到会话
            session['share_link'] = collection_link
            session['collection_data'] = collection_data
            
            current_app.logger.info(f"已生成Google Drive合集链接: {collection_link}")
            if shortcuts_count > 1:
                flash(f'Your {shortcuts_count} photos have been shared via Google Drive!', 'success')
            else:
                flash('Your photo has been shared via Google Drive!', 'success')
            
        except ImportError:
            current_app.logger.error("未找到Google Drive同步模块")
            flash('Google Drive integration is not available.', 'error')
        except Exception as e:
            current_app.logger.error(f"生成Google Drive链接时出错: {str(e)}", exc_info=True)
            flash('An error occurred while creating Google Drive link.', 'error')
    
    except Exception as e:
        current_app.logger.error(f"处理Google Drive链接时出错: {str(e)}", exc_info=True)
        flash('An error occurred while processing your request.', 'error')
    
    # 重定向到感谢页面
    return redirect(url_for('client.thank_you', access_link=project.access_link))

# 添加清理临时文件的函数
def cleanup_temp_files(directory, max_age_hours=24, file_extensions=None):
    """
    清理指定目录中超过给定时间的文件
    
    参数:
        directory (str): 要清理的目录路径
        max_age_hours (int): 文件最大保存时间（小时）
        file_extensions (list): 要清理的文件扩展名列表，如['.zip', '.jpg']
    """
    if not os.path.exists(directory):
        return
        
    # 计算截止时间点
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    # 遍历目录中的所有文件
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        
        # 只处理文件（跳过子目录）
        if os.path.isfile(file_path):
            # 如果指定了文件扩展名，则只处理匹配的文件
            if file_extensions and not any(filename.endswith(ext) for ext in file_extensions):
                continue
                
            # 获取文件修改时间
            mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            # 如果文件超过最大保存时间，则删除
            if mod_time < cutoff_time:
                try:
                    os.remove(file_path)
                    current_app.logger.info(f"已删除临时文件: {filename}")
                except Exception as e:
                    current_app.logger.error(f"删除文件 {filename} 时出错: {str(e)}") 