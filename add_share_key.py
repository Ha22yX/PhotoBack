import sqlite3
import os
import sys
from datetime import datetime

# 设置stdout编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# 数据库文件路径
db_path = 'instance/photoweb.sqlite'

print(f"开始数据库迁移: {datetime.now()}")
print(f"目标数据库: {db_path}")

# 确保数据库文件存在
if not os.path.exists(db_path):
    print(f"错误: 数据库文件 {db_path} 不存在")
    exit(1)

# 连接到SQLite数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 检查share_key列是否存在
    cursor.execute("PRAGMA table_info(selection)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'share_key' not in columns:
        print("正在添加share_key列到selection表...")
        # 先添加普通列，不带UNIQUE约束
        cursor.execute("ALTER TABLE selection ADD COLUMN share_key VARCHAR(20)")
        conn.commit()
        
        # 然后创建唯一索引
        try:
            print("添加唯一索引到share_key列...")
            cursor.execute("CREATE UNIQUE INDEX idx_selection_share_key ON selection(share_key) WHERE share_key IS NOT NULL")
            conn.commit()
            print("唯一索引添加成功!")
        except sqlite3.Error as e:
            print(f"添加索引时出错: {e}")
            # 这个错误不会阻止整个迁移
            
        print("列添加成功!")
    else:
        print("share_key列已存在")
    
    # 验证修改
    cursor.execute("PRAGMA table_info(selection)")
    columns = [column[1] for column in cursor.fetchall()]
    print(f"selection表当前列: {columns}")
    
except sqlite3.Error as e:
    print(f"数据库错误: {e}")
    conn.rollback()
finally:
    # 关闭连接
    conn.close()
    print(f"数据库迁移完成: {datetime.now()}") 