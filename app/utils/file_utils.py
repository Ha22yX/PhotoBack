import os
import time
import logging
import zipfile
from flask import current_app
from datetime import datetime, timedelta

def cleanup_temp_files(temp_dir, max_age_hours=24, file_extensions=None):
    """
    清理临时目录中超过指定时间的旧文件
    
    Args:
        temp_dir: 临时文件目录路径
        max_age_hours: 最大保留时间（小时），默认24小时
        file_extensions: 要清理的文件扩展名列表，如 ['.zip', '.jpg']，默认为None（清理所有文件）
        
    Returns:
        int: 已删除的文件数量
    """
    if not os.path.exists(temp_dir):
        logging.info(f"临时目录 {temp_dir} 不存在，无需清理")
        return 0
        
    now = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0
    
    try:
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            
            # 仅处理文件，跳过目录
            if os.path.isfile(file_path):
                # 如果指定了文件扩展名，则仅清理匹配的文件
                if file_extensions and not any(filename.lower().endswith(ext.lower()) for ext in file_extensions):
                    continue
                    
                # 获取文件的最后修改时间
                file_age = now - os.path.getmtime(file_path)
                
                # 如果文件超过最大保留时间，则删除
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    logging.info(f"已删除旧文件: {file_path}")
                    deleted_count += 1
                    
        logging.info(f"清理完成: 已删除 {deleted_count} 个文件")
        return deleted_count
    except Exception as e:
        logging.error(f"清理临时文件时出错: {str(e)}")
        return deleted_count

def cleanup_all_temp_folders(base_dir=None, max_age_hours=24):
    """
    清理项目中所有临时文件夹
    
    Args:
        base_dir: 项目基础目录，默认为None（使用当前应用的根目录）
        max_age_hours: 最大保留时间（小时），默认24小时
        
    Returns:
        dict: 包含每个目录清理结果的字典
    """
    if base_dir is None:
        try:
            base_dir = current_app.root_path
        except RuntimeError:
            # 如果在应用上下文外调用，使用相对路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 定义需要清理的临时文件夹及对应的文件类型
    temp_folders = {
        os.path.join(base_dir, 'static', 'uploads', 'temp'): ['.zip'],  # ZIP文件
        os.path.join(base_dir, 'static', 'uploads', 'thumbnails'): ['.jpg', '.jpeg', '.png', '.gif'],  # 缩略图
        os.path.join(base_dir, 'static', 'logs'): ['.log']  # 日志文件
    }
    
    results = {}
    
    for folder, extensions in temp_folders.items():
        if os.path.exists(folder):
            count = cleanup_temp_files(folder, max_age_hours, extensions)
            results[folder] = count
        else:
            results[folder] = 0
            logging.info(f"临时目录 {folder} 不存在，跳过清理")
    
    return results 