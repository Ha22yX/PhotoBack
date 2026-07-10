from app import create_app, db
from app.models import User, Project, Photo, Selection, SelectedPhoto

# 创建应用上下文
app = create_app()
with app.app_context():
    # 更新数据库结构
    db.create_all()
    print("数据库结构已更新，添加了缩略图字段") 