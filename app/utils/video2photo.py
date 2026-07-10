import cv2
import os
import argparse

def extract_first_frame(video_path, output_path=None):
    """
    从视频中提取第一帧作为缩略图
    
    参数:
        video_path: 视频文件路径
        output_path: 输出图像路径，默认为视频文件名+'.jpg'
    
    返回:
        输出图像的路径
    """
    # 验证视频文件是否存在
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    
    # 如果未指定输出路径，则使用视频文件名
    if output_path is None:
        video_filename = os.path.splitext(os.path.basename(video_path))[0]
        output_path = f"{video_filename}_thumbnail.jpg"
    
    # 确保输出路径有正确的扩展名（.jpg, .png等）
    _, ext = os.path.splitext(output_path)
    if not ext:
        # 如果没有扩展名，添加.jpg
        output_path = f"{output_path}.jpg"
    elif ext.lower() not in ['.jpg', '.jpeg', '.png', '.bmp']:
        # 如果扩展名不受支持，替换为.jpg
        output_path = os.path.splitext(output_path)[0] + '.jpg'
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 打开视频文件
    video_capture = cv2.VideoCapture(video_path)
    
    # 检查视频是否成功打开
    if not video_capture.isOpened():
        raise Exception(f"无法打开视频文件: {video_path}")
    
    # 读取第一帧
    success, frame = video_capture.read()
    
    if not success:
        video_capture.release()
        raise Exception(f"无法读取视频帧: {video_path}")
    
    # 保存第一帧作为图像
    try:
        cv2.imwrite(output_path, frame)
        print(f"已成功将视频首帧保存为: {output_path}")
    except Exception as e:
        video_capture.release()
        raise Exception(f"保存图像失败: {str(e)}")
    
    # 释放视频对象
    video_capture.release()
    
    return output_path

def video_to_thumbnail(video_path, output_path=None):
    """
    整体函数：输入视频文件路径，返回提取的首帧图片路径
    
    参数:
        video_path: 视频文件路径
        output_path: 输出图像路径，默认为视频文件名+'.jpg'
    
    返回:
        输出图像的路径，如果出错则返回None
    """
    try:
        # 确保输出路径结尾是.jpg
        if output_path:
            base_name, ext = os.path.splitext(output_path)
            if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.bmp']:
                output_path = base_name + '.jpg'
                
        # 首先检查文件是否已经存在
        if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"缩略图已存在: {output_path}")
            return output_path
                
        result = extract_first_frame(video_path, output_path)
        
        # 如果提取过程成功返回路径，检查文件是否真的创建了
        if result and os.path.exists(result) and os.path.getsize(result) > 0:
            return result
            
        # 即使extract_first_frame没有返回结果，也再次检查文件是否存在
        if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"缩略图文件存在，尽管函数没有明确成功: {output_path}")
            return output_path
            
        return None
    except Exception as e:
        print(f"错误: {e}")
        # 即使发生异常，也检查文件是否被创建
        if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"尽管有错误，缩略图文件已成功创建: {output_path}")
            return output_path
        return None

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='从视频提取第一帧作为缩略图')
    parser.add_argument('video_path', help='输入视频文件的路径')
    parser.add_argument('-o', '--output', help='输出缩略图的路径（可选）')
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 使用整体函数处理
    thumbnail_path = video_to_thumbnail(args.video_path, args.output)
    if thumbnail_path:
        print(f"缩略图已保存到: {thumbnail_path}")

if __name__ == "__main__":
    main() 