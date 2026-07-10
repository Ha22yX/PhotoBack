#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import create_app
from app.models import db, Photo
from app.utils.video2photo import video_to_thumbnail
import os

def generate_thumbnails_for_videos():
    """为没有缩略图的视频生成缩略图并更新数据库"""
    
    # 创建Flask应用上下文
    app = create_app()
    
    with app.app_context():
        # 查询所有没有缩略图的视频
        videos = Photo.query.filter_by(file_type='video', thumbnail_filename=None).all()
        print(f'找到 {len(videos)} 个没有缩略图的视频')
        
        for video in videos:
            # 获取视频文件路径
            video_path = os.path.join(app.static_folder, 'uploads', video.filename)
            
            # 检查视频文件是否存在
            if not os.path.exists(video_path):
                print(f'视频文件不存在: {video_path}')
                continue
                
            # 创建缩略图文件名和路径
            video_name = os.path.splitext(video.filename)[0]
            thumbnails_dir = os.path.join(app.static_folder, 'uploads', 'thumbnails')
            
            # 确保缩略图目录存在
            os.makedirs(thumbnails_dir, exist_ok=True)
            
            # 检查可能存在的缩略图文件
            possible_thumbnails = [
                f"{video_name}_thumb.jpg",
                f"{video_name}_thumbnail.jpg",
                f"thumb_{video_name}.jpg",
                f"{video_name}.jpg"
            ]
            
            # 查找是否已经存在缩略图文件
            found_thumbnail = None
            for thumb_name in possible_thumbnails:
                thumb_path = os.path.join(thumbnails_dir, thumb_name)
                if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                    found_thumbnail = thumb_path
                    print(f'找到已存在的缩略图: {thumb_path}')
                    break
                    
            if found_thumbnail:
                # 更新数据库记录
                video.thumbnail_filename = os.path.basename(found_thumbnail)
                db.session.commit()
                print(f'更新数据库记录使用已存在的缩略图: {os.path.basename(found_thumbnail)}')
                continue
            
            # 如果没找到缩略图，生成新的
            thumbnail_filename = f"{video_name}_thumb.jpg"
            thumbnail_path = os.path.join(thumbnails_dir, thumbnail_filename)
            
            print(f'正在为视频 {video.original_filename} 生成缩略图...')
            try:
                # 生成缩略图
                result = video_to_thumbnail(video_path, thumbnail_path)
                
                if result and os.path.exists(result):
                    # 更新数据库
                    video.thumbnail_filename = os.path.basename(result)
                    db.session.commit()
                    print(f'成功生成缩略图: {result}')
                else:
                    print(f'生成缩略图失败: {video_path}')
                    
                    # 尝试使用ffmpeg作为备用方法
                    try:
                        import subprocess
                        ffmpeg_cmd = f'ffmpeg -i "{video_path}" -vframes 1 -an -s 800x450 -ss 0 "{thumbnail_path}"'
                        subprocess.call(ffmpeg_cmd, shell=True)
                        
                        if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                            # 更新数据库
                            video.thumbnail_filename = os.path.basename(thumbnail_path)
                            db.session.commit()
                            print(f'使用ffmpeg成功生成缩略图: {thumbnail_path}')
                        else:
                            print(f'ffmpeg也失败了: {video_path}')
                    except Exception as e:
                        print(f'ffmpeg处理出错: {str(e)}')
            
            except Exception as e:
                print(f'处理视频 {video.original_filename} 时出错: {str(e)}')
                # 回滚以防止部分更新
                db.session.rollback()

if __name__ == "__main__":
    generate_thumbnails_for_videos() 