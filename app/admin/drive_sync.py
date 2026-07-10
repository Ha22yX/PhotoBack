import os
from flask import current_app
from app.models import Project, Photo
from app import db
from app.admin.cloud import GoogleDriveManager
import logging
import traceback
import time

# Configure logging
logger = logging.getLogger(__name__)

class DriveSync:
    """
    Class to handle synchronization between the local app and Google Drive
    """
    
    def __init__(self, token_path=None):
        """Initialize the drive sync with an optional token path"""
        logger.info("初始化DriveSync")
        if not token_path:
            token_path = os.path.join(current_app.instance_path, 'google_token.json')
            logger.info(f"使用默认token路径: {token_path}")
        
        try:
            # 检查token文件是否存在
            if os.path.exists(token_path):
                logger.info(f"Token文件存在: {token_path}")
            else:
                logger.warning(f"Token文件不存在: {token_path}，这将触发OAuth认证流程")
            
            self.drive_manager = GoogleDriveManager(token_path=token_path)
            self.upload_folder = current_app.config['UPLOAD_FOLDER']
            logger.info(f"DriveSync初始化成功，上传文件夹: {self.upload_folder}")
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"DriveSync初始化失败: {str(e)}\n{stack_trace}")
            raise

    def _resolve_project_folder(self, project):
        """
        Resolve a project's Drive folder with validation and repair.

        Ensures drive_folder_id is valid for the project, otherwise finds or
        recreates the correct folder and updates the DB record.
        """
        project_id_str = str(project.id)
        folder_id = getattr(project, 'drive_folder_id', None)

        if folder_id:
            folder_meta = self.drive_manager.get_folder_metadata(folder_id)
            if folder_meta and self.drive_manager.folder_matches_project(folder_meta, project_id_str):
                logger.info(f"确认项目Drive文件夹有效: {folder_id}")
                return folder_id

            if folder_meta:
                logger.warning(
                    "项目Drive文件夹不匹配，ID: %s, 名称: %s",
                    folder_id,
                    folder_meta.get('name')
                )
            else:
                logger.warning(f"项目Drive文件夹无效或不存在: {folder_id}")

        folder_id = self.drive_manager.find_project_folder(project_id_str, project.title)
        if folder_id:
            logger.info(f"找到匹配的项目Drive文件夹: {folder_id}")
            if project.drive_folder_id != folder_id:
                project.drive_folder_id = folder_id
                db.session.commit()
            return folder_id

        logger.info("未找到项目Drive文件夹，准备创建新文件夹")
        folder_id = self.drive_manager.sync_project(project_id_str, project.title)
        if folder_id:
            project.drive_folder_id = folder_id
            db.session.commit()
        return folder_id
    
    def sync_project_creation(self, project=None):
        """
        同步未同步的项目到Google Drive。
        使用项目名称作为文件夹名称，确保所有项目文件夹都在Projects主文件夹内。
        
        Args:
            project: 可选，如果提供则只同步此项目，否则同步所有未同步的项目
        
        Returns:
            如果指定了单个项目，返回创建的文件夹ID；否则返回None
        """
        try:
            # 如果提供了特定项目，只同步该项目
            if project:
                current_app.logger.info(f"开始同步项目 '{project.title}' (ID: {project.id}) 到Google Drive")
                
                try:
                    # 修正：使用项目的title属性
                    folder_id = self.drive_manager.sync_project(str(project.id), project.title)
                    
                    if folder_id:
                        # 更新项目的drive_folder_id
                        project.drive_folder_id = folder_id
                        db.session.commit()
                        current_app.logger.info(f"项目 '{project.title} (ID: {project.id})' 成功同步到Google Drive，文件夹ID: {folder_id}")
                        return folder_id
                    else:
                        current_app.logger.error(f"无法为项目 '{project.title} (ID: {project.id})' 创建Google Drive文件夹")
                        return None
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"同步项目 '{project.title} (ID: {project.id})' 时发生错误: {str(e)}")
                    return None
            
            # 否则同步所有未同步的项目
            # 获取所有未同步的项目
            # 使用drive_folder_id=None来查找未同步的项目
            unsynced_projects = db.session.query(Project).filter(Project.drive_folder_id == None).all()
            
            # 记录同步状态
            current_app.logger.info(f"开始同步未同步的项目到Google Drive")
            current_app.logger.info(f"找到 {len(unsynced_projects)} 个未同步的项目")
            
            # 初始化Google Drive管理器
            try:
                drive_manager = GoogleDriveManager()
                current_app.logger.info("Google Drive管理器初始化成功")
            except Exception as e:
                current_app.logger.error(f"初始化Google Drive管理器失败: {str(e)}")
                return None
            
            # 为每个未同步的项目创建文件夹
            for project in unsynced_projects:
                try:
                    # 修正：使用项目的title属性而非name
                    folder_id = drive_manager.sync_project(str(project.id), project.title)
                    
                    if folder_id:
                        # 更新项目的drive_folder_id
                        project.drive_folder_id = folder_id
                        db.session.commit()
                        current_app.logger.info(f"项目 '{project.title} (ID: {project.id})' 成功同步到Google Drive，文件夹ID: {folder_id}")
                    else:
                        current_app.logger.error(f"无法为项目 '{project.title} (ID: {project.id})' 创建Google Drive文件夹")
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"同步项目 '{project.title} (ID: {project.id})' 时发生错误: {str(e)}")
            
            current_app.logger.info("项目同步完成")
            return None
            
        except Exception as e:
            current_app.logger.error(f"同步项目创建到Google Drive时发生错误: {str(e)}")
            return None
    
    def sync_photo_upload(self, photo):
        """
        Sync a newly uploaded photo to Google Drive
        
        Args:
            photo: The Photo model instance
            
        Returns:
            The Google Drive file ID
        """
        logger.info(f"开始同步新上传的照片 {photo.id} - {photo.original_filename} 到Google Drive")
        start_time = time.time()
        
        try:
            # Get project and ensure it has a Drive folder ID
            project = photo.project
            if not project:
                logger.error(f"照片 {photo.id} 没有关联的项目")
                return None
                
            logger.info(f"照片所属项目: '{project.title}' (ID: {project.id})")

            # Resolve and validate project folder
            folder_id = self._resolve_project_folder(project)
            if not folder_id:
                logger.error(f"为项目 {project.id} 获取Drive文件夹失败")
                return None
            
            # Get the compressed file path
            photo_path = os.path.join(self.upload_folder, photo.filename)
            logger.info(f"照片文件路径: {photo_path}")
            
            if not os.path.exists(photo_path):
                logger.error(f"照片文件不存在: {photo_path}")
                # 检查其他可能的路径
                alt_path = os.path.join(current_app.instance_path, 'uploads', photo.filename)
                logger.info(f"尝试替代路径: {alt_path}")
                if os.path.exists(alt_path):
                    photo_path = alt_path
                    logger.info(f"在替代路径找到文件: {photo_path}")
                else:
                    return None
            
            file_size = os.path.getsize(photo_path)
            logger.info(f"照片文件大小: {file_size/1024/1024:.2f} MB")
            
            # 检查照片是否已有Drive文件ID
            drive_file_id = getattr(photo, 'drive_file_id', None)
            if drive_file_id:
                logger.info(f"照片已有Drive文件ID: {drive_file_id}，检查文件是否存在")
                # TODO: 验证文件是否存在，目前没有直接方法，需要通过API请求
            
            # Upload the photo
            logger.info(f"开始上传照片 {photo.filename}")
            file_id = self.drive_manager.sync_photo(
                photo.filename, 
                photo.original_filename, 
                photo_path, 
                folder_id
            )
            
            if not file_id:
                logger.error(f"上传照片 {photo.id} 到Google Drive失败")
                return None
            
            # Store the file ID in the photo metadata
            logger.info(f"上传成功，将文件ID: {file_id} 保存到照片记录")
            photo.drive_file_id = file_id
            db.session.commit()
            
            elapsed_time = time.time() - start_time
            logger.info(f"照片 {photo.id} 同步完成，耗时: {elapsed_time:.2f}秒，文件ID: {file_id}")
            return file_id
        except Exception as e:
            stack_trace = traceback.format_exc()
            elapsed_time = time.time() - start_time
            logger.error(f"同步照片 {photo.id} 到Drive失败: {str(e)}，耗时: {elapsed_time:.2f}秒\n{stack_trace}")
            return None
    
    def sync_photo_deletion(self, photo):
        """
        Remove a deleted photo from Google Drive
        
        Args:
            photo: The Photo model instance being deleted
            
        Returns:
            Boolean indicating success
        """
        logger.info(f"开始从Google Drive删除照片 {photo.id} - {photo.original_filename}")
        start_time = time.time()
        
        try:
            # If photo doesn't have a Drive file ID or project has no Drive folder, nothing to do
            drive_file_id = getattr(photo, 'drive_file_id', None)
            if drive_file_id:
                logger.info(f"使用照片的Drive文件ID删除: {drive_file_id}")
                result = self.drive_manager.delete_file(drive_file_id)
                elapsed_time = time.time() - start_time
                if result:
                    logger.info(f"照片 {photo.id} 从Drive删除成功，耗时: {elapsed_time:.2f}秒")
                else:
                    logger.error(f"照片 {photo.id} 从Drive删除失败，耗时: {elapsed_time:.2f}秒")
                return result
                
            # If no direct file ID, try to find by name in project folder
            logger.info(f"照片没有Drive文件ID，尝试通过文件名和项目文件夹查找")
            project = photo.project
            if not project:
                logger.error(f"照片 {photo.id} 没有关联的项目，无法删除")
                return False
                
            folder_id = getattr(project, 'drive_folder_id', None)
            if not folder_id:
                logger.error(f"项目 {project.id} 没有Drive文件夹ID，无法删除照片")
                return False
            
            logger.info(f"尝试在项目文件夹 {folder_id} 中查找并删除文件: {photo.filename}")
            # Try to find and delete by filename
            result = self.drive_manager.remove_file_if_exists(photo.filename, folder_id)
            elapsed_time = time.time() - start_time
            
            if result:
                logger.info(f"照片 {photo.id} 从Drive删除成功，耗时: {elapsed_time:.2f}秒")
            else:
                logger.info(f"照片 {photo.id} 在Drive中未找到或删除失败，耗时: {elapsed_time:.2f}秒")
            
            return result
        except Exception as e:
            stack_trace = traceback.format_exc()
            elapsed_time = time.time() - start_time
            logger.error(f"从Drive删除照片 {photo.id} 失败: {str(e)}，耗时: {elapsed_time:.2f}秒\n{stack_trace}")
            return False
    
    def sync_project_deletion(self, project):
        """
        Remove a deleted project and all its photos from Google Drive
        
        Args:
            project: The Project model instance being deleted
            
        Returns:
            Boolean indicating success
        """
        logger.info(f"开始从Google Drive删除项目 '{project.title}' (ID: {project.id})")
        start_time = time.time()
        
        try:
            folder_id = getattr(project, 'drive_folder_id', None)
            if not folder_id:
                logger.info(f"项目没有Drive文件夹ID，尝试通过项目ID查找")
                # Try to find by project ID
                folder_id = self.drive_manager.find_project_folder(str(project.id), project.title)
                
            if folder_id:
                logger.info(f"找到项目文件夹ID: {folder_id}，准备删除")
                result = self.drive_manager.remove_folder_with_contents(folder_id)
                elapsed_time = time.time() - start_time
                
                if result:
                    logger.info(f"项目 {project.id} 文件夹从Drive删除成功，耗时: {elapsed_time:.2f}秒")
                else:
                    logger.error(f"项目 {project.id} 文件夹从Drive删除失败，耗时: {elapsed_time:.2f}秒")
                
                return result
            else:
                logger.info(f"未找到项目 {project.id} 的Drive文件夹，无需删除")
                return False
        except Exception as e:
            stack_trace = traceback.format_exc()
            elapsed_time = time.time() - start_time
            logger.error(f"从Drive删除项目 {project.id} 失败: {str(e)}，耗时: {elapsed_time:.2f}秒\n{stack_trace}")
            return False
    
    def full_sync_project(self, project):
        """
        Perform a complete sync of a project and all its photos to Google Drive
        
        Args:
            project: The Project model instance
            
        Returns:
            Tuple of (folder_id, number of photos synced)
        """
        logger.info(f"开始全量同步项目 '{project.title}' (ID: {project.id}) 到Google Drive")
        start_time = time.time()
        photos_count = len(project.photos)
        logger.info(f"项目包含 {photos_count} 张照片")
        
        try:
            # Create or get project folder
            project_id_str = str(project.id)
            logger.info(f"查找或创建项目文件夹: {project_id_str}")

            folder_id = self._resolve_project_folder(project)
            if not folder_id:
                logger.error("创建项目文件夹失败")
                return None, 0
            
            # Prepare photo data for sync
            logger.info(f"准备照片数据进行同步")
            photos_data = []
            
            # 记录检索到的照片数据，用于诊断
            valid_photos = 0
            missing_files = 0
            
            for i, photo in enumerate(project.photos):
                logger.info(f"处理照片 {i+1}/{photos_count}: {photo.filename}")
                
                # 检查照片文件是否存在
                photo_path = os.path.join(self.upload_folder, photo.filename)
                if not os.path.exists(photo_path):
                    logger.warning(f"照片文件不存在: {photo_path}")
                    missing_files += 1
                    continue
                
                # 检查文件大小
                file_size = os.path.getsize(photo_path)
                if file_size == 0:
                    logger.warning(f"照片文件大小为0: {photo_path}")
                    missing_files += 1
                    continue
                
                logger.info(f"有效照片: {photo.filename}, 大小: {file_size/1024/1024:.2f} MB")
                photos_data.append({
                    'filename': photo.filename,
                    'original_filename': photo.original_filename
                })
                valid_photos += 1
            
            logger.info(f"准备同步 {valid_photos} 张有效照片，跳过 {missing_files} 张缺失照片")
            
            # Sync all photos
            logger.info(f"开始同步所有照片到Drive文件夹: {folder_id}")
            uploaded_files = self.drive_manager.sync_project_photos(
                project_id_str,
                photos_data,
                self.upload_folder,
                project.title
            )
            
            sync_success_count = len(uploaded_files)
            logger.info(f"成功同步 {sync_success_count}/{valid_photos} 张照片")
            
            # Update photo records with Drive file IDs
            logger.info(f"更新照片记录的Drive文件ID")
            updated_photos = 0
            for photo in project.photos:
                if photo.filename in uploaded_files:
                    drive_file_id = uploaded_files[photo.filename]
                    logger.debug(f"更新照片 {photo.id} 的Drive文件ID: {drive_file_id}")
                    photo.drive_file_id = drive_file_id
                    updated_photos += 1
            
            logger.info(f"更新了 {updated_photos} 张照片的Drive文件ID")
            db.session.commit()
            
            elapsed_time = time.time() - start_time
            logger.info(f"项目 '{project.title}' (ID: {project.id}) 全量同步完成，"
                       f"耗时: {elapsed_time:.2f}秒，同步照片: {sync_success_count}/{photos_count}")
            
            return folder_id, sync_success_count
        except Exception as e:
            stack_trace = traceback.format_exc()
            elapsed_time = time.time() - start_time
            logger.error(f"全量同步项目 {project.id} 失败: {str(e)}，耗时: {elapsed_time:.2f}秒\n{stack_trace}")
            return None, 0

# Create a singleton instance
drive_sync = None

def get_drive_sync():
    """Get or create the drive sync singleton instance"""
    global drive_sync
    logger.info("获取DriveSync实例")
    
    if drive_sync is None:
        logger.info("DriveSync实例不存在，创建新实例")
        try:
            # 优先使用app/admin目录下的token.json
            token_path = os.path.join(os.path.dirname(__file__), 'token.json')
            if os.path.exists(token_path):
                logger.info(f"找到token.json: {token_path}")
                drive_sync = DriveSync(token_path=token_path)
                logger.info("DriveSync实例创建成功")
            else:
                # 如果app/admin目录下没有token.json，尝试查找其他位置
                logger.warning(f"app/admin目录下没有token.json，尝试使用默认路径")
                drive_sync = DriveSync()
                logger.info("DriveSync实例创建成功")
        except FileNotFoundError as e:
            # 处理找不到token文件的情况
            error_msg = f"Google Drive同步需要先完成认证。错误: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except ValueError as e:
            # 处理token无效的情况
            error_msg = f"Google Drive认证失败: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"创建DriveSync实例失败: {str(e)}\n{stack_trace}")
            # 转换为更友好的错误消息
            raise RuntimeError(f"Google Drive同步功能初始化失败: {str(e)}")
    else:
        logger.debug("使用现有DriveSync实例")
    
    return drive_sync 