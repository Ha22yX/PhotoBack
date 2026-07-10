"""
测试Google Drive集成修复

使用方法:
1. 确保已将token.json文件放在app/admin目录下
2. 从项目根目录运行: python -m app.admin.test_drive
"""

import os
import sys
import logging

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_drive')

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

def test_drive_integration():
    """
    测试Google Drive集成是否正常工作，不需要浏览器认证
    """
    logger.info("====== 开始测试Google Drive集成 ======")
    
    try:
        # 导入GoogleDriveManager
        from app.admin.cloud import GoogleDriveManager
        
        # 查找token路径
        script_dir = os.path.dirname(os.path.abspath(__file__))
        token_path = os.path.join(script_dir, 'token.json')
        
        if not os.path.exists(token_path):
            logger.error(f"找不到token.json文件: {token_path}")
            return False
        
        logger.info(f"使用token路径: {token_path}")
        
        # 初始化GoogleDriveManager
        logger.info("初始化GoogleDriveManager...")
        drive_manager = GoogleDriveManager(token_path=token_path)
        
        # 测试创建文件夹
        logger.info("测试创建文件夹...")
        folder_name = "test_folder_" + os.urandom(4).hex()
        folder_id = drive_manager.create_folder(folder_name)
        
        if not folder_id:
            logger.error("创建文件夹失败")
            return False
            
        logger.info(f"文件夹创建成功，ID: {folder_id}")
        
        # 测试列出文件夹内容
        logger.info("测试列出文件夹内容...")
        files = drive_manager.list_files_in_folder(folder_id)
        logger.info(f"文件夹内容: {files}")
        
        # 测试删除文件夹
        logger.info("测试删除文件夹...")
        result = drive_manager.remove_folder_with_contents(folder_id)
        
        if result:
            logger.info("文件夹删除成功")
        else:
            logger.error("文件夹删除失败")
            return False
            
        logger.info("✅ Google Drive集成测试成功")
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    result = test_drive_integration()
    if result:
        print("\n✅ 测试成功: Google Drive集成可以正常工作，无需浏览器认证")
        sys.exit(0)
    else:
        print("\n❌ 测试失败: Google Drive集成存在问题")
        sys.exit(1) 