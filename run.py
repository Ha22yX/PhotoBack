import os
from datetime import datetime
from app import create_app

app = create_app()

if __name__ == '__main__':
    print(f"应用启动，时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    app.run(debug=True, host='0.0.0.0', port=5000)  # 使用端口 5001 
        