import sqlite3
import os

# 数据库文件路径
db_path = 'app.db'

# 确保数据库文件存在
if not os.path.exists(db_path):
    print(f"数据库文件 {db_path} 不存在")
    exit(1)

# 连接到SQLite数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 检查thumbnail_filename列是否存在
    cursor.execute("PRAGMA table_info(photo)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'thumbnail_filename' not in columns:
        print("添加thumbnail_filename列到photo表...")
        cursor.execute("ALTER TABLE photo ADD COLUMN thumbnail_filename TEXT")
        conn.commit()
        print("列添加成功!")
    else:
        print("thumbnail_filename列已存在")
    
except sqlite3.Error as e:
    print(f"数据库错误: {e}")
    conn.rollback()
finally:
    # 关闭连接
    conn.close()
    print("数据库迁移完成") 