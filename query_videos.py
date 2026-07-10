from app import create_app
from app.models import db, Photo
import os

def main():
    app = create_app()
    with app.app_context():
        videos = Photo.query.filter_by(file_type='video').all()
        print(f'找到 {len(videos)} 个视频记录')
        
        for v in videos:
            print(f'ID: {v.id}, 文件名: {v.filename}, 缩略图: {v.thumbnail_filename}, 原始文件名: {v.original_filename}')
            
            # 检查文件是否存在
            video_path = os.path.join(app.static_folder, 'uploads', v.filename)
            video_exists = os.path.exists(video_path)
            
            # 检查缩略图是否存在
            thumbnail_exists = False
            if v.thumbnail_filename:
                thumbnail_path = os.path.join(app.static_folder, 'uploads', 'thumbnails', v.thumbnail_filename)
                thumbnail_exists = os.path.exists(thumbnail_path)
                
            print(f'  - 视频文件存在: {video_exists}')
            print(f'  - 缩略图文件存在: {thumbnail_exists}')
            if thumbnail_exists:
                print(f'  - 缩略图路径: {os.path.join(app.static_folder, "uploads", "thumbnails", v.thumbnail_filename)}')

if __name__ == "__main__":
    main() 