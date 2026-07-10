import os
import shutil
import zipfile
from PIL import Image
from flask import current_app

def generate_thumbnail(image_path, output_path, size=(300, 200)):
    """
    生成图片缩略图
    
    参数:
    image_path: 原图路径
    output_path: 缩略图保存路径
    size: 缩略图尺寸，默认300x200
    
    返回:
    缩略图文件路径
    """
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 打开图片并生成缩略图
        with Image.open(image_path) as img:
            # 保持比例
            img.thumbnail(size, Image.Resampling.LANCZOS)
            # 保存缩略图
            img.save(output_path, quality=95)
        
        return output_path
    except Exception as e:
        print(f"生成缩略图失败: {e}")
        return None

def is_image_file(filename):
    """检查文件是否是图片"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def create_thumbnail(image_path, thumb_path, size=(300, 200)):
    """
    创建缩略图
    
    参数：
    image_path: 原图路径
    thumb_path: 缩略图保存路径
    size: 缩略图尺寸，默认300x200
    """
    try:
        # 确保缩略图目录存在
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # 打开原图
        img = Image.open(image_path)
        
        # 保持宽高比创建缩略图
        img.thumbnail(size, Image.Resampling.LANCZOS)
        
        # 保存缩略图
        img.save(thumb_path, optimize=True, quality=95)
        
        return True
    except Exception as e:
        print(f"创建缩略图失败: {e}")
        return False

def get_thumbnail_path(filename):
    """
    根据原图文件名获取缩略图路径
    """
    # 拆分文件名和扩展名
    name, ext = os.path.splitext(filename)
    return f"{name}_thumb{ext}"

def optimize_image(input_path, output_path=None, quality=85, target_size_mb=5, preserve_size=False):
    """
    优化图片大小但不损失画质 - 智能压缩模式
    :param input_path: 输入图片路径
    :param output_path: 输出图片路径，如果为None则覆盖原图
    :param quality: 图片质量，范围1-100，默认85（高质量）
    :param target_size_mb: 目标文件大小（MB），默认5MB
    :param preserve_size: 是否保持原始尺寸
    :return: 压缩率百分比，0表示无压缩或失败
    """
    # 规范化路径
    input_path = os.path.normpath(input_path)
    
    if output_path is None:
        output_path = input_path
    else:
        output_path = os.path.normpath(output_path)
    
    # 确保文件存在并创建输出目录
    if not os.path.exists(input_path):
        return 0
    
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    try:
        # 打开图片
        img = Image.open(input_path)
        img_format = img.format or 'JPEG'
        
        # 获取原始图片信息
        original_size = os.path.getsize(input_path)
        original_size_mb = original_size / (1024 * 1024)
        original_width, original_height = img.size
        
        # 如果原图已经足够小且需要保持原始尺寸，直接使用原图
        if preserve_size and original_size_mb <= target_size_mb:
            if input_path != output_path:
                shutil.copy2(input_path, output_path)
            return 0
            
        # 如果用户提供了质量参数，优先使用用户设置的质量
        optimal_quality = quality
        
        # 只有当用户没有明确指定质量(使用默认值85时)，才使用智能压缩策略
        if quality == 85:  # 默认质量参数
            # 智能压缩策略 - 根据图片大小和尺寸选择最佳质量参数
            if original_size_mb > 100:  # 超大图片(>100MB)
                if original_width > 4000 or original_height > 4000:
                    optimal_quality = 70  # 超大尺寸，使用较低质量
                else:
                    optimal_quality = 75  # 普通超大图片
            elif original_size_mb > 50:  # 大图片(50-100MB)
                if original_width > 3000 or original_height > 3000:
                    optimal_quality = 75
                else:
                    optimal_quality = 80
            elif original_size_mb > 20:  # 中大图片(20-50MB)
                if original_width > 2000 or original_height > 2000:
                    optimal_quality = 80
                else:
                    optimal_quality = 85
            elif original_size_mb > 10:  # 中等图片(10-20MB)
                if original_width > 1500 or original_height > 1500:
                    optimal_quality = 85
                else:
                    optimal_quality = 87
            elif original_size_mb > 5:   # 小图片(5-10MB)
                if original_width > 1000 or original_height > 1000:
                    optimal_quality = 87
                else:
                    optimal_quality = 90
            else:                        # 极小图片(<5MB)
                optimal_quality = 92
            
        # 尺寸调整（仅针对超大图片）
        process_img = img
        if not preserve_size and (original_width > 4000 or original_height > 4000):
            # 更合理的尺寸调整，使用4000px作为上限
            max_dimension = 4000
            ratio = min(max_dimension / original_width, max_dimension / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            process_img = img.resize((new_width, new_height), Image.LANCZOS)
            
        # 临时文件路径
        temp_output = output_path + ".temp"
            
        # 根据不同格式执行压缩
        if img_format in ['JPEG', 'JPG']:
            # JPEG图片压缩
            process_img.save(temp_output, 
                    format=img_format,
                    quality=optimal_quality, 
                    optimize=True,
                    progressive=True,
                    subsampling=0 if optimal_quality > 80 else 2)
        elif img_format == 'PNG':
            # PNG图片压缩
            process_img.save(temp_output,
                    format=img_format,
                    optimize=True,
                    quality=optimal_quality if not preserve_size else None)
        else:
            # 其他格式
            process_img.save(temp_output,
                    format=img_format,
                    quality=optimal_quality,
                    optimize=True)
        
        # 计算压缩率
        compressed_size = os.path.getsize(temp_output)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        # 移动临时文件到最终位置
        if os.path.exists(output_path):
            os.remove(output_path)
        shutil.move(temp_output, output_path)
        
        return compression_ratio
            
    except Exception as e:
        print(f"图片压缩失败: {str(e)}")
        # 错误处理 - 如果压缩失败，直接复制原图
        if input_path != output_path and os.path.exists(input_path):
            shutil.copy2(input_path, output_path)
        return 0

def create_photos_zip(photos, output_path):
    """
    将选中的照片打包成ZIP文件
    
    参数:
    photos: 照片列表，每个元素是(文件路径, 原始文件名)的元组
    output_path: ZIP文件保存路径
    
    返回:
    ZIP文件路径，如果失败则返回None
    """
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 创建ZIP文件
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path, original_filename in photos:
                if os.path.exists(file_path):
                    # 使用原始文件名作为ZIP中的文件名
                    zipf.write(file_path, original_filename)
        
        return output_path
    except Exception as e:
        print(f"创建ZIP文件失败: {e}")
        return None 