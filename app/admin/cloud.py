from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import json
import shutil
import logging
import io
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from flask import current_app
import time
import traceback
import socket
import ssl
import httplib2
from datetime import datetime

# 获取logger
logger = logging.getLogger('photoweb.google_drive')

SCOPES = ['https://www.googleapis.com/auth/drive']

def google_client_config():
    """Build Google OAuth client config from environment variables."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    project_id = os.getenv("GOOGLE_PROJECT_ID", "photoback-client").strip()
    if not client_id or not client_secret:
        raise ValueError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET before starting Google Drive authorization.")
    return {
        "installed": {
            "client_id": client_id,
            "project_id": project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
        }
    }

class GoogleDriveManager:
    def _escape_query_value(self, value: str) -> str:
        """
        Escape characters that break Drive query strings.
        Single quotes must be escaped as \', backslashes doubled.
        """
        if value is None:
            return ""
        return value.replace("\\", "\\\\").replace("'", "\\'")
    def __init__(self, token_path=None):
        logger.info("初始化GoogleDriveManager")
        start_time = time.time()
        
        # 如果没有提供token路径，使用默认路径
        if not token_path:
            # 先尝试查找当前目录下的token.json
            if os.path.exists('token.json'):
                token_path = 'token.json'
                logger.info(f"使用当前目录的token.json")
            elif os.path.exists(os.path.join(os.path.dirname(__file__), 'token.json')):
                token_path = os.path.join(os.path.dirname(__file__), 'token.json')
                logger.info(f"使用app/admin目录下的token.json")
            else:
                token_path = os.path.join(current_app.instance_path, 'google_token.json')
                logger.info(f"使用默认token路径: {token_path}")
        
        try:
            self.creds = None
            # 检查token文件是否存在并加载凭据
            if os.path.exists(token_path):
                logger.info(f"读取token文件: {token_path}")
                try:
                    with open(token_path, 'r') as token_file:
                        token_data = json.load(token_file)
                        self.creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                    logger.info("成功从token文件加载凭据")
                except Exception as e:
                    logger.error(f"读取token文件失败: {str(e)}")
                    raise ValueError(f"Token文件无效: {str(e)}")
            else:
                # 如果token文件不存在，给出明确的错误信息而不是自动启动授权流程
                error_msg = f"找不到Google认证Token: {token_path}。请先在本地环境完成授权，然后将生成的token.json文件放到正确位置。"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # 如果凭据有效但已过期，尝试刷新
            if self.creds and self.creds.expired and self.creds.refresh_token:
                logger.info("凭据已过期，尝试刷新")
                try:
                    self.creds.refresh(Request())
                    logger.info("凭据刷新成功")
                    
                    # 保存刷新后的凭据
                    with open(token_path, 'w') as token:
                        token.write(self.creds.to_json())
                    logger.info(f"刷新后的凭据已保存到: {token_path}")
                except Exception as e:
                    logger.error(f"凭据刷新失败: {str(e)}")
                    raise ValueError(f"无法刷新凭据: {str(e)}")
            
            # 构建带重试次数和重试间隔的httplib2对象
            http = httplib2.Http(timeout=30)
            
            # 添加SSL证书验证设置
            try:
                # 设置SSL上下文
                ssl_context = ssl.create_default_context()
                # 如果需要，可以禁用证书验证(生产环境不推荐)
                # ssl_context.check_hostname = False
                # ssl_context.verify_mode = ssl.CERT_NONE
                http.ssl_context = ssl_context
            except Exception as e:
                logger.warning(f"SSL配置设置失败: {str(e)}，将使用默认设置")
            
            # 创建Drive API服务
            self.service = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            elapsed_time = time.time() - start_time
            logger.info(f"Google Drive服务初始化成功，耗时: {elapsed_time:.2f}秒")
            
            # 测试连接
            try:
                about = self.service.about().get(fields='user,storageQuota').execute()
                quota = about.get('storageQuota', {})
                used = int(quota.get('usage', 0)) / (1024 * 1024 * 1024)  # in GB
                total = int(quota.get('limit', 0)) / (1024 * 1024 * 1024)  # in GB
                logger.info(f"Google Drive 连接成功，用户: {about.get('user', {}).get('displayName', 'Unknown')}")
                logger.info(f"存储状态: 已使用 {used:.2f}GB / 总容量 {total:.2f}GB")
            except Exception as e:
                logger.warning(f"获取Google Drive信息失败: {str(e)}")
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"初始化Google Drive Manager失败: {str(e)}\n{stack_trace}")
            raise

    def upload_file(self, filename, filepath, folder_id=None):
        logger.info(f"上传文件到Drive: {filename}")
        start_time = time.time()
        
        try:
            # Check if file exists
            if not os.path.exists(filepath):
                logger.error(f"要上传的文件不存在: {filepath}")
                return None
            
            # Log file size
            file_size = os.path.getsize(filepath)
            logger.info(f"文件大小: {file_size/1024/1024:.2f} MB")
            
            # 检查文件是否已存在于文件夹中
            if folder_id:
                # 首先检查文件名是否存在
                query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
                logger.info(f"检查文件是否已存在于文件夹 {folder_id}")
                results = self.service.files().list(q=query, fields="files(id, name, size)").execute()
                files = results.get('files', [])
                
                if files:
                    # 找到同名文件
                    file_id = files[0]['id']
                    file_size_drive = int(files[0].get('size', 0)) if 'size' in files[0] else 0
                    
                    # 如果文件大小相同，很可能是同一个文件
                    if abs(file_size - file_size_drive) < 1024:  # 允许1KB的误差
                        logger.info(f"文件已存在且大小相似，ID: {file_id}，跳过上传")
                        return file_id
                    else:
                        logger.info(f"文件名相同但大小不同 (本地: {file_size/1024/1024:.2f}MB, 云端: {file_size_drive/1024/1024:.2f}MB)，将上传新版本")
            
            # Prepare file metadata
            file_metadata = {'name': filename}
            if folder_id:
                file_metadata['parents'] = [folder_id]
                logger.info(f"文件将上传到文件夹: {folder_id}")
            
            # Detect MIME type based on file extension
            from mimetypes import guess_type
            mime_type, _ = guess_type(filepath)
            if not mime_type:
                mime_type = 'application/octet-stream'
            logger.info(f"文件MIME类型: {mime_type}")
            
            # Upload the file
            logger.info(f"开始上传文件: {filename}")
            media = MediaFileUpload(filepath, mimetype=mime_type, resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            )
            
            # Track upload progress
            response = None
            last_progress = 0
            while response is None:
                status, response = file.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress - last_progress >= 20:  # Log every 20% progress
                        logger.info(f"上传进度: {progress}%")
                        last_progress = progress
            
            file_id = response.get('id')
            elapsed_time = time.time() - start_time
            upload_speed = file_size / (1024 * 1024) / (elapsed_time if elapsed_time > 0 else 1)
            
            logger.info(f"文件上传成功，ID: {file_id}，耗时: {elapsed_time:.2f}秒，速度: {upload_speed:.2f} MB/s")
            return file_id
        
        except HttpError as error:
            logger.error(f"上传文件HTTP错误: {error}")
            return None
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"上传文件失败: {str(e)}\n{stack_trace}")
            return None

    def upload_files_bulk(self, file_paths, parent_folder_id=None):
        logger.info(f"批量上传 {len(file_paths)} 个文件到文件夹ID: {parent_folder_id or '根目录'}")
        ids = []
        for i, path in enumerate(file_paths):
            logger.info(f"上传第 {i+1}/{len(file_paths)} 个文件: {path}")
            file_id = self.upload_file(path, parent_folder_id)
            if file_id:
                ids.append(file_id)
            else:
                logger.warning(f"文件 {path} 上传失败，跳过")
        
        logger.info(f"批量上传完成，成功: {len(ids)}/{len(file_paths)}")
        return ids

    def create_folder(self, folder_name, parent_id=None, max_retries=3, retry_delay=2):
        """
        创建文件夹并处理SSL错误，提供重试机制
        
        Args:
            folder_name: 要创建的文件夹名称
            parent_id: 父文件夹ID (可选)
            max_retries: 最大重试次数
            retry_delay: 重试间隔(秒)
            
        Returns:
            创建的文件夹ID，或者None
        """
        logger.info(f"创建文件夹: {folder_name}" + (f" 在父文件夹: {parent_id}" if parent_id else ""))
        
        retries = 0
        while retries <= max_retries:
            try:
                # Check if folder already exists
                existing_folder = self.find_folder_by_name(folder_name, parent_id)
                if existing_folder:
                    logger.info(f"文件夹已存在，ID: {existing_folder}")
                    return existing_folder
                
                # Create folder
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                if parent_id:
                    folder_metadata['parents'] = [parent_id]
                
                folder = self.service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                folder_id = folder.get('id')
                logger.info(f"文件夹创建成功，ID: {folder_id}")
                
                # Verify folder was created properly
                try:
                    self.service.files().get(fileId=folder_id).execute()
                    logger.info(f"文件夹验证成功: {folder_id}")
                except HttpError as e:
                    logger.error(f"文件夹创建后无法访问: {str(e)}")
                    return None
                
                return folder_id
            
            except HttpError as error:
                logger.error(f"创建文件夹HTTP错误: {error}")
                if retries < max_retries:
                    retries += 1
                    logger.info(f"重试 ({retries}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                return None
                
            except ssl.SSLError as ssl_error:
                error_msg = str(ssl_error)
                logger.error(f"SSL错误: {error_msg}")
                
                if "WRONG_VERSION_NUMBER" in error_msg:
                    logger.error("SSL版本不匹配，可能是代理或网络问题")
                
                if retries < max_retries:
                    retries += 1
                    # 指数退避，随重试次数增加等待时间
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"SSL错误，将在 {wait_time} 秒后重试 ({retries}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                return None
                
            except socket.error as sock_error:
                logger.error(f"网络连接错误: {str(sock_error)}")
                if retries < max_retries:
                    retries += 1
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"网络错误，将在 {wait_time} 秒后重试 ({retries}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                return None
                
            except Exception as e:
                stack_trace = traceback.format_exc()
                logger.error(f"创建文件夹失败: {str(e)}\n{stack_trace}")
                if retries < max_retries:
                    retries += 1
                    logger.info(f"未知错误，重试 ({retries}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                return None
        
        # 如果所有重试都失败
        logger.error(f"创建文件夹失败，已达到最大重试次数 {max_retries}")
        return None

    def rename_file(self, file_id, new_name):
        logger.info(f"重命名文件 ID: {file_id} 为: {new_name}")
        try:
            file = {'name': new_name}
            updated_file = self.service.files().update(fileId=file_id, body=file, fields='id, name').execute()
            logger.info(f"文件重命名成功: {updated_file.get('id')} - {updated_file.get('name')}")
            return updated_file
        except Exception as e:
            logger.error(f"重命名文件失败: {str(e)}", exc_info=True)
            return None

    def delete_file(self, file_id):
        logger.info(f"删除文件: {file_id}")
        
        try:
            # Verify file exists before attempting to delete
            try:
                self.service.files().get(fileId=file_id).execute()
                logger.info(f"验证文件存在: {file_id}")
            except HttpError as e:
                if e.resp.status == 404:
                    logger.warning(f"文件不存在，无需删除: {file_id}")
                    return True
                else:
                    raise
            
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"文件删除成功: {file_id}")
            return True
            
        except HttpError as error:
            logger.error(f"删除文件HTTP错误: {error}")
            return False
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"删除文件失败: {str(e)}\n{stack_trace}")
            return False

    def create_shareable_link(self, file_ids):
        logger.info(f"为 {len(file_ids)} 个文件创建共享链接")
        links = {}
        for i, file_id in enumerate(file_ids):
            logger.info(f"处理第 {i+1}/{len(file_ids)} 个文件的共享链接, ID: {file_id}")
            try:
                self.service.permissions().create(
                    fileId=file_id,
                    body={
                        'type': 'anyone',
                        'role': 'reader'
                    }
                ).execute()
                logger.debug(f"权限设置成功，获取共享链接")
                
                file = self.service.files().get(fileId=file_id, fields='webViewLink').execute()
                link = file.get('webViewLink')
                links[file_id] = link
                logger.info(f"文件 {file_id} 共享链接创建成功: {link}")
            except Exception as e:
                logger.error(f"为文件 {file_id} 创建共享链接失败: {str(e)}", exc_info=True)
        
        logger.info(f"共享链接创建完成，成功: {len(links)}/{len(file_ids)}")
        return links

    def create_project_folder(self, project_name):
        logger.info(f"创建项目文件夹: {project_name}")
        return self.create_folder(project_name)

    def create_selection_folder_and_share(self, project_id, selected_files):
        logger.info(f"在项目 {project_id} 中创建选择文件夹并共享 {len(selected_files)} 个文件")
        selection_folder_id = self.create_folder("Selected_Photos", parent_id=project_id)
        if not selection_folder_id:
            logger.error("创建选择文件夹失败")
            return {}
            
        logger.info(f"选择文件夹创建成功，ID: {selection_folder_id}")
        shared_ids = []
        
        for i, file_id in enumerate(selected_files):
            logger.info(f"复制第 {i+1}/{len(selected_files)} 个文件 ID: {file_id} 到选择文件夹")
            try:
                copied = self.service.files().copy(fileId=file_id, body={'parents': [selection_folder_id]}).execute()
                copied_id = copied.get('id')
                shared_ids.append(copied_id)
                logger.info(f"文件复制成功，新ID: {copied_id}")
            except Exception as e:
                logger.error(f"复制文件 {file_id} 失败: {str(e)}", exc_info=True)
        
        logger.info(f"开始为 {len(shared_ids)} 个文件创建共享链接")
        return self.create_shareable_link(shared_ids)

    def list_files_in_folder(self, folder_id):
        logger.info(f"列出文件夹 {folder_id} 中的文件")
        
        try:
            query = f"'{folder_id}' in parents and trashed = false"
            results = self.service.files().list(
                q=query,
                fields="files(id, name, mimeType, size)"
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                logger.info(f"文件夹 {folder_id} 中没有文件")
                return []
            
            logger.info(f"文件夹中有 {len(files)} 个文件")
            return files
            
        except HttpError as error:
            logger.error(f"列出文件夹内容HTTP错误: {error}")
            return None

    def get_folder_metadata(self, folder_id):
        """Fetch folder metadata for validation."""
        logger.info(f"获取文件夹元数据: {folder_id}")
        try:
            folder = self.service.files().get(
                fileId=folder_id,
                fields='id,name,mimeType,parents,appProperties'
            ).execute()
            if folder.get('mimeType') != 'application/vnd.google-apps.folder':
                logger.warning(f"ID {folder_id} 不是文件夹类型: {folder.get('mimeType')}")
                return None
            return folder
        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"文件夹不存在: {folder_id}")
                return None
            logger.error(f"获取文件夹元数据HTTP错误: {error}")
            return None
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"获取文件夹元数据失败: {str(e)}\n{stack_trace}")
            return None

    def folder_matches_project(self, folder_metadata, project_id):
        """Validate that a folder belongs to a project."""
        if not folder_metadata:
            return False
        app_props = folder_metadata.get('appProperties') or {}
        if app_props.get('project_id') == str(project_id):
            return True
        folder_name = folder_metadata.get('name', '')
        return f"(ID: {project_id})" in folder_name

    def find_folder_by_name(self, folder_name, parent_id=None, max_retries=3, retry_delay=2):
        """
        查找文件夹并处理SSL错误，提供重试机制
        
        Args:
            folder_name: 要查找的文件夹名称
            parent_id: 父文件夹ID (可选)
            max_retries: 最大重试次数
            retry_delay: 重试间隔(秒)
            
        Returns:
            找到的文件夹ID，或者None
        """
        logger.info(f"查找文件夹: {folder_name}" + (f" 在父文件夹: {parent_id}" if parent_id else ""))
        
        retries = 0
        while retries <= max_retries:
            try:
                # Create query to find folder
                query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_name}' and trashed = false"
                if parent_id:
                    query += f" and '{parent_id}' in parents"
                
                # Execute query
                results = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id, name)',
                    pageSize=1
                ).execute()
                
                items = results.get('files', [])
                if not items:
                    logger.info(f"未找到文件夹: {folder_name}")
                    return None
                
                folder_id = items[0]['id']
                logger.info(f"找到文件夹，ID: {folder_id}")
                return folder_id
                
            except HttpError as error:
                logger.error(f"查找文件夹HTTP错误: {error}")
                if retries < max_retries:
                    retries += 1
                    logger.info(f"重试 ({retries}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                return None
                
            except ssl.SSLError as ssl_error:
                error_msg = str(ssl_error)
                logger.error(f"SSL错误: {error_msg}")
                
                if "WRONG_VERSION_NUMBER" in error_msg:
                    logger.error("SSL版本不匹配，可能是代理或网络问题")
                
                if retries < max_retries:
                    retries += 1
                    # 指数退避，随重试次数增加等待时间
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"SSL错误，将在 {wait_time} 秒后重试 ({retries}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                return None
                
            except socket.error as sock_error:
                logger.error(f"网络连接错误: {str(sock_error)}")
                if retries < max_retries:
                    retries += 1
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"网络错误，将在 {wait_time} 秒后重试 ({retries}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                return None
                
            except Exception as e:
                stack_trace = traceback.format_exc()
                logger.error(f"查找文件夹失败: {str(e)}\n{stack_trace}")
                if retries < max_retries:
                    retries += 1
                    logger.info(f"未知错误，重试 ({retries}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                return None
        
        # 如果所有重试都失败
        logger.error(f"查找文件夹失败，已达到最大重试次数 {max_retries}")
        return None

    def find_file_by_name(self, filename, folder_id=None):
        """Find a file by its name within a folder, returns file ID if found, None otherwise"""
        log_msg = f"在{'文件夹 ' + folder_id if folder_id else '根目录'}中按名称查找文件: {filename}"
        logger.info(log_msg)
        
        try:
            query = f"name = '{filename}' and trashed = false"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            
            logger.debug(f"查询: {query}")
            result = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = result.get('files', [])
            
            if files:
                file_id = files[0]['id']
                logger.info(f"找到文件 '{filename}', ID: {file_id}")
                return file_id
            else:
                logger.info(f"未找到文件 '{filename}'")
                return None
        except Exception as e:
            logger.error(f"查找文件失败: {str(e)}", exc_info=True)
            return None

    def _ensure_projects_parent_folder(self):
        """
        确保Projects主文件夹存在，如果不存在则创建它
        
        Returns:
            str: Projects文件夹的ID，如果创建失败返回None
        """
        try:
            # 先检查是否已存在Projects文件夹
            current_app.logger.info("检查Projects主文件夹是否存在")
            query = f"name='Projects' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                # 已存在Projects文件夹
                folder_id = items[0]['id']
                current_app.logger.info(f"找到已存在的Projects主文件夹，ID: {folder_id}")
                return folder_id
            
            # 不存在，创建新的Projects文件夹
            current_app.logger.info("未找到Projects主文件夹，准备创建")
            folder_metadata = {
                'name': 'Projects',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            current_app.logger.info(f"已创建Projects主文件夹，ID: {folder_id}")
            return folder_id
            
        except Exception as e:
            current_app.logger.error(f"确保Projects主文件夹存在时发生错误: {str(e)}")
            return None
            
    def sync_project(self, project_id, project_name):
        """
        为项目创建Google Drive文件夹，位于Projects主文件夹下
        
        Args:
            project_id (int): 项目ID，用于确保文件夹名称的唯一性
            project_name (str): 项目名称，用作文件夹的主要名称
            
        Returns:
            str: 创建的文件夹ID，如果创建失败返回None
        """
        try:
            # 确保Projects主文件夹存在
            parent_id = self._ensure_projects_parent_folder()
            if not parent_id:
                current_app.logger.error("无法获取或创建Projects主文件夹，项目文件夹创建失败")
                return None
                
            # 先检查是否已有同名/同ID的项目文件夹，避免重复创建
            existing_folder = self.find_project_folder(project_id, project_name)
            if existing_folder:
                current_app.logger.info(f"复用已存在的项目文件夹: {existing_folder}")
                return existing_folder
            
            # 使用项目名称和ID格式化文件夹名称（实际创建使用原始名称）
            formatted_name = f"{project_name} (ID: {project_id})"
            current_app.logger.info(f"为项目创建Google Drive文件夹: {formatted_name}")
            
            # 在Projects文件夹下创建项目文件夹
            folder_metadata = {
                'name': formatted_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id],
                # 使用 appProperties 记录项目ID，便于唯一识别
                'appProperties': {
                    'project_id': str(project_id)
                }
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            current_app.logger.info(f"已创建项目文件夹，ID: {folder_id}")
            return folder_id
            
        except Exception as e:
            current_app.logger.error(f"创建项目文件夹时发生错误: {str(e)}")
            return None

    def sync_photo(self, filename, original_filename, filepath, folder_id):
        logger.info(f"同步照片: {filename} (原始名称: {original_filename}) 到文件夹: {folder_id}")
        
        try:
            # 同时检查原始文件名和系统文件名是否存在于文件夹中
            # 先查找原始文件名
            query = f"name = '{original_filename}' and '{folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            if files:
                file_id = files[0]['id']
                logger.info(f"照片已存在于文件夹中（原始文件名匹配），ID: {file_id}")
                return file_id
                
            # 再查找系统文件名
            query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            if files:
                file_id = files[0]['id']
                logger.info(f"照片已存在于文件夹中（系统文件名匹配），ID: {file_id}")
                return file_id
            
            # 文件不存在，准备上传（使用原始文件名）
            logger.info(f"照片不存在，准备上传: {original_filename}")
            return self.upload_file(original_filename, filepath, folder_id)
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"同步照片失败: {str(e)}\n{stack_trace}")
            return None

    def sync_project_photos(self, project_id, photos_data, upload_folder, project_name=None):
        logger.info(f"同步项目 {project_id} 的所有照片，共 {len(photos_data)} 张")
        start_time = time.time()
        
        try:
            # Get or create project folder
            folder_id = self.find_project_folder(project_id, project_name)
            if not folder_id:
                logger.info(f"项目文件夹不存在，创建新文件夹")
                # 使用传入的项目名称，如果没有则使用默认值
                folder_name = project_name if project_name else f"项目 {project_id}"
                folder_id = self.sync_project(project_id, folder_name)
                if not folder_id:
                    logger.error(f"无法创建项目文件夹，同步失败")
                    return {}
            
            # List existing files in the folder to avoid re-uploading
            logger.info(f"获取文件夹 {folder_id} 中的现有文件")
            existing_files = self.list_files_in_folder(folder_id)
            logger.info(f"文件夹中已有 {len(existing_files) if existing_files else 0} 个文件")
            
            # 创建文件名到文件信息的映射，便于快速查找
            file_map = {}
            if existing_files:
                for file in existing_files:
                    file_map[file['name']] = file
            
            # Initialize results
            results = {}
            processed = 0
            skipped = 0
            
            # Process each photo
            total_photos = len(photos_data)
            for i, photo_data in enumerate(photos_data):
                filename = photo_data['filename']
                original_filename = photo_data['original_filename']
                
                logger.info(f"处理照片 {i+1}/{total_photos}: {filename}")
                
                # 首先检查原始文件名是否存在
                if original_filename in file_map:
                    file_id = file_map[original_filename]['id']
                    logger.info(f"照片已存在于Drive中（原始文件名匹配），ID: {file_id}")
                    results[filename] = file_id
                    skipped += 1
                    continue
                
                # 再检查系统文件名是否存在
                if filename in file_map:
                    file_id = file_map[filename]['id']
                    logger.info(f"照片已存在于Drive中（系统文件名匹配），ID: {file_id}")
                    results[filename] = file_id
                    skipped += 1
                    continue
                
                # 文件不存在，准备上传
                filepath = os.path.join(upload_folder, filename)
                if not os.path.exists(filepath):
                    logger.warning(f"照片文件不存在: {filepath}")
                    continue
                
                # 检查文件大小
                file_size = os.path.getsize(filepath)
                if file_size == 0:
                    logger.warning(f"照片文件大小为0，跳过: {filepath}")
                    continue
                
                logger.info(f"上传照片: {original_filename}")
                file_id = self.upload_file(original_filename, filepath, folder_id)
                
                if file_id:
                    results[filename] = file_id
                    processed += 1
                    
                    # 添加到映射以避免后续重复检查
                    file_map[original_filename] = {'id': file_id, 'name': original_filename}
                    
                    # Log progress every 10 photos or at the end
                    if processed % 10 == 0 or processed == total_photos:
                        elapsed = time.time() - start_time
                        logger.info(f"已上传 {processed}/{total_photos} 张照片，耗时: {elapsed:.2f}秒")
            
            elapsed_time = time.time() - start_time
            logger.info(f"项目照片同步完成，上传 {processed} 张，跳过 {skipped} 张，共 {total_photos} 张，耗时: {elapsed_time:.2f}秒")
            return results
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"同步项目照片失败: {str(e)}\n{stack_trace}")
            return {}

    def remove_file_if_exists(self, filename, folder_id):
        logger.info(f"检查并删除文件 {filename} 如果存在于文件夹 {folder_id}")
        
        try:
            # Check if file exists in the folder
            query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            if not files:
                logger.info(f"文件 {filename} 不存在于文件夹中")
                return True
            
            # Delete file
            file_id = files[0]['id']
            logger.info(f"找到文件，ID: {file_id}，准备删除")
            
            return self.delete_file(file_id)
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"检查并删除文件失败: {str(e)}\n{stack_trace}")
            return False

    def remove_folder_with_contents(self, folder_id):
        logger.info(f"删除文件夹及其内容: {folder_id}")
        
        try:
            # Verify folder exists
            try:
                folder = self.service.files().get(fileId=folder_id).execute()
                if folder.get('mimeType') != 'application/vnd.google-apps.folder':
                    logger.error(f"ID {folder_id} 不是文件夹")
                    return False
                logger.info(f"验证文件夹存在: {folder_id}")
            except HttpError as e:
                if e.resp.status == 404:
                    logger.warning(f"文件夹不存在，无需删除: {folder_id}")
                    return True
                else:
                    raise
            
            # List files in the folder
            files = self.list_files_in_folder(folder_id)
            logger.info(f"文件夹包含 {len(files) if files else 0} 个文件")
            
            # Delete each file
            if files:
                for file in files:
                    file_id = file['id']
                    if file['mimeType'] == 'application/vnd.google-apps.folder':
                        logger.info(f"删除子文件夹: {file_id}")
                        self.remove_folder_with_contents(file_id)
                    else:
                        logger.info(f"删除文件: {file_id}")
                        self.delete_file(file_id)
            
            # Delete the folder itself
            logger.info(f"删除空文件夹: {folder_id}")
            return self.delete_file(folder_id)
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"删除文件夹及其内容失败: {str(e)}\n{stack_trace}")
            return False

    def create_shared_view(self, file_ids):
        """
        为多个文件创建共享视图，不需要创建额外文件夹
        
        Args:
            file_ids: 要共享的文件ID列表
            
        Returns:
            包含共享视图URL的字典
        """
        logger.info(f"为 {len(file_ids)} 个文件创建共享视图")
        
        # 1. 共享每个文件
        successfully_shared = []
        for i, file_id in enumerate(file_ids):
            try:
                logger.info(f"设置文件 {i+1}/{len(file_ids)} (ID: {file_id}) 的共享权限")
                
                # 检查文件是否存在
                try:
                    self.service.files().get(fileId=file_id).execute()
                except Exception as e:
                    logger.warning(f"文件 {file_id} 不存在，跳过: {str(e)}")
                    continue
                    
                # 设置共享权限
                self.service.permissions().create(
                    fileId=file_id,
                    body={'type': 'anyone', 'role': 'reader'},
                    fields='id'
                ).execute()
                
                # 获取文件信息
                file = self.service.files().get(fileId=file_id, fields='webViewLink,name').execute()
                file_link = file.get('webViewLink')
                file_name = file.get('name')
                
                logger.info(f"文件 '{file_name}' (ID: {file_id}) 共享权限设置成功，链接: {file_link}")
                successfully_shared.append(file_id)
                
            except Exception as e:
                logger.error(f"为文件 {file_id} 设置共享权限失败: {str(e)}", exc_info=True)
        
        # 2. 如果没有成功共享的文件，返回空
        if not successfully_shared:
            logger.error("没有文件成功共享")
            return {}
        
        # 3. 获取每个文件的单独链接
        file_links = {}
        for file_id in successfully_shared:
            try:
                file = self.service.files().get(fileId=file_id, fields='webViewLink,name').execute()
                file_links[file_id] = {
                    'link': file.get('webViewLink'),
                    'name': file.get('name')
                }
            except Exception as e:
                logger.error(f"获取文件 {file_id} 的链接失败: {str(e)}")
        
        # 4. 创建共享视图URL
        # 方式1: 使用Drive UI共享视图
        ids_param = ",".join(successfully_shared)
        view_url = f"https://drive.google.com/open?ids={ids_param}"
        logger.info(f"创建共享视图链接: {view_url}")
        
        # 返回结果
        return {
            'view': view_url,               # 主共享视图链接
            'files': file_links,            # 单个文件的链接信息
            'count': len(successfully_shared)  # 成功共享的文件数量
        }
        
    def batch_share_files(self, file_ids):
        """
        批量共享多个文件并获取每个文件的链接
        
        Args:
            file_ids: 要共享的文件ID列表
            
        Returns:
            包含每个文件链接的字典
        """
        logger.info(f"批量共享 {len(file_ids)} 个文件")
        
        # 共享结果
        shared_files = []
        file_links = {}
        
        # 为每个文件设置共享权限并获取链接
        for i, file_id in enumerate(file_ids):
            try:
                logger.info(f"处理第 {i+1}/{len(file_ids)} 个文件 (ID: {file_id})")
                
                # 检查文件是否存在
                try:
                    file_info = self.service.files().get(fileId=file_id).execute()
                    file_name = file_info.get('name', f'File-{i+1}')
                except Exception as e:
                    logger.warning(f"文件 {file_id} 不存在，跳过: {str(e)}")
                    continue
                
                # 设置共享权限
                self.service.permissions().create(
                    fileId=file_id,
                    body={'type': 'anyone', 'role': 'reader'},
                    fields='id'
                ).execute()
                
                # 获取共享链接
                file = self.service.files().get(fileId=file_id, fields='webViewLink,name').execute()
                link = file.get('webViewLink')
                name = file.get('name', file_name)
                
                logger.info(f"文件 '{name}' 共享成功，链接: {link}")
                
                # 保存结果
                shared_files.append(file_id)
                file_links[file_id] = {
                    'link': link,
                    'name': name
                }
                
            except Exception as e:
                logger.error(f"共享文件 {file_id} 失败: {str(e)}", exc_info=True)
        
        logger.info(f"批量共享完成，成功: {len(shared_files)}/{len(file_ids)}")
        
        return {
            'files': file_links,
            'count': len(shared_files)
        }

    def create_shortcuts_collection(self, file_ids, collection_name="Selected_Photos"):
        """
        创建一个包含快捷方式的共享文件夹，无需复制原始文件
        
        Args:
            file_ids: 要添加到合集中的文件ID列表
            collection_name: 合集文件夹名称
            
        Returns:
            包含合集文件夹链接的字典
        """
        logger.info(f"为 {len(file_ids)} 个文件创建快捷方式合集")
        
        try:
            # 0. 确保主合集目录存在
            collections_parent = self._ensure_collections_parent_folder()
            if not collections_parent:
                logger.error("无法创建或获取快捷方式合集主目录")
                return {}
            
            # 1. 创建合集文件夹
            folder_metadata = {
                'name': collection_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [collections_parent]  # 放入主合集目录
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id,name'
            ).execute()
            
            collection_id = folder.get('id')
            collection_name = folder.get('name')
            logger.info(f"在主合集目录中创建合集文件夹成功: '{collection_name}' (ID: {collection_id})")
            
            # 1.5 先共享原始文件，确保用户有权访问
            logger.info(f"设置 {len(file_ids)} 个原始文件的共享权限")
            for i, file_id in enumerate(file_ids):
                try:
                    # 检查文件是否已经共享
                    try:
                        permissions = self.service.permissions().list(fileId=file_id).execute()
                        already_shared = False
                        for permission in permissions.get('permissions', []):
                            if permission.get('type') == 'anyone':
                                already_shared = True
                                break
                                
                        if already_shared:
                            logger.info(f"文件 {file_id} 已经设置了共享权限，跳过")
                            continue
                    except Exception as e:
                        logger.warning(f"获取文件 {file_id} 权限失败: {str(e)}，将尝试设置共享权限")
                    
                    # 设置共享权限
                    self.service.permissions().create(
                        fileId=file_id,
                        body={'type': 'anyone', 'role': 'reader'},
                        fields='id'
                    ).execute()
                    logger.info(f"文件 {file_id} 共享权限设置成功 ({i+1}/{len(file_ids)})")
                except Exception as e:
                    logger.error(f"为原始文件 {file_id} 设置共享权限失败: {str(e)}")
            
            # 2. 为每个选中的文件创建快捷方式
            shortcuts = []
            file_info = {}
            
            for i, file_id in enumerate(file_ids):
                try:
                    # 获取文件信息以用于快捷方式命名
                    file = self.service.files().get(fileId=file_id, fields='name').execute()
                    file_name = file.get('name', f'File-{i+1}')
                    
                    # 创建快捷方式
                    shortcut_metadata = {
                        'name': file_name,  # 使用原文件名
                        'mimeType': 'application/vnd.google-apps.shortcut',
                        'shortcutDetails': {
                            'targetId': file_id
                        },
                        'parents': [collection_id]
                    }
                    
                    shortcut = self.service.files().create(
                        body=shortcut_metadata, 
                        fields='id,name'
                    ).execute()
                    
                    shortcut_id = shortcut.get('id')
                    shortcuts.append(shortcut_id)
                    file_info[shortcut_id] = {'name': file_name, 'original_id': file_id}
                    
                    logger.info(f"为文件 '{file_name}' (ID: {file_id}) 创建快捷方式成功 (ID: {shortcut_id})")
                except Exception as e:
                    logger.error(f"为文件 {file_id} 创建快捷方式失败: {str(e)}", exc_info=True)
            
            # 3. 设置文件夹共享权限
            self.service.permissions().create(
                fileId=collection_id,
                body={'type': 'anyone', 'role': 'reader'},
                fields='id'
            ).execute()
            logger.info(f"设置合集文件夹 '{collection_name}' 共享权限成功")
            
            # 4. 获取文件夹共享链接
            folder = self.service.files().get(
                fileId=collection_id, 
                fields='webViewLink'
            ).execute()
            
            folder_link = folder.get('webViewLink')
            logger.info(f"获取合集文件夹 '{collection_name}' 共享链接成功: {folder_link}")
            
            # 返回结果
            return {
                'collection_id': collection_id,
                'collection_name': collection_name,
                'collection_link': folder_link,
                'shortcuts_count': len(shortcuts),
                'shortcuts': file_info
            }
            
        except Exception as e:
            logger.error(f"创建快捷方式合集失败: {str(e)}", exc_info=True)
            return {}
            
    def _ensure_collections_parent_folder(self):
        """
        确保存在一个用于存放所有快捷方式合集的主目录
        如果不存在则创建，返回目录ID
        """
        COLLECTIONS_FOLDER_NAME = "PhotoWeb Collections"
        
        try:
            # 1. 查找是否已存在
            query = f"name = '{COLLECTIONS_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.service.files().list(q=query, spaces='drive', fields='files(id,name)').execute()
            
            items = results.get('files', [])
            if items:
                folder_id = items[0]['id']
                logger.info(f"找到现有合集主目录: {folder_id}")
                return folder_id
                
            # 2. 不存在则创建
            logger.info(f"创建快捷方式合集主目录: {COLLECTIONS_FOLDER_NAME}")
            folder_metadata = {
                'name': COLLECTIONS_FOLDER_NAME,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id,name'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"合集主目录创建成功: {folder_id}")
            return folder_id
            
        except Exception as e:
            logger.error(f"创建或获取合集主目录失败: {str(e)}", exc_info=True)
            return None

    def find_project_folder(self, project_id, project_name=None):
        """
        查找项目文件夹，首先尝试使用格式化名称查找，然后尝试使用项目ID
        
        Args:
            project_id: 项目ID
            project_name: 项目名称（可选）
            
        Returns:
            找到的项目文件夹ID，如果未找到则返回None
        """
        try:
            # 确保Projects主文件夹存在
            parent_id = self._ensure_projects_parent_folder()
            if not parent_id:
                logger.error("无法获取Projects主文件夹，无法查找项目文件夹")
                return None
            
            # 优先按 appProperties 精确匹配项目ID，避免名称冲突和重复创建
            logger.info(f"尝试通过appProperties查找项目文件夹，项目ID: {project_id}")
            query_app_prop = (
                "mimeType = 'application/vnd.google-apps.folder' "
                f"and appProperties has {{ key='project_id' and value='{project_id}' }} "
                f"and '{parent_id}' in parents and trashed = false"
            )
            try:
                results = self.service.files().list(
                    q=query_app_prop,
                    spaces='drive',
                    fields='files(id, name, appProperties)',
                    pageSize=1
                ).execute()
                items = results.get('files', [])
                if items:
                    folder_id = items[0]['id']
                    logger.info(f"通过appProperties找到项目文件夹: {items[0].get('name')}，ID: {folder_id}")
                    return folder_id
            except Exception as e:
                logger.warning(f"按appProperties查找项目文件夹失败，将回退到名称查找: {str(e)}")
            
            # 如果提供了项目名称，首先尝试查找格式化的文件夹名称
            if project_name:
                safe_name = self._escape_query_value(project_name)
                formatted_name = f"{safe_name} (ID: {project_id})"
                logger.info(f"尝试查找项目文件夹: {formatted_name}")
                
                query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{formatted_name}' and '{parent_id}' in parents and trashed = false"
                results = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='files(id, name)',
                    pageSize=1
                ).execute()
                
                items = results.get('files', [])
                if items:
                    folder_id = items[0]['id']
                    logger.info(f"找到项目文件夹 '{formatted_name}'，ID: {folder_id}")
                    return folder_id
            
            # 然后查找包含项目ID的任何文件夹
            logger.info(f"未找到格式化名称的文件夹，搜索包含项目ID {project_id} 的文件夹")
            query = f"mimeType = 'application/vnd.google-apps.folder' and name contains '(ID: {project_id})' and '{parent_id}' in parents and trashed = false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            items = results.get('files', [])
            if items:
                folder_id = items[0]['id']
                logger.info(f"找到项目文件夹: {items[0]['name']}，ID: {folder_id}")
                return folder_id
            
            logger.info(f"未找到项目 {project_id} 的文件夹")
            return None
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"查找项目文件夹失败: {str(e)}\n{stack_trace}")
            return None
