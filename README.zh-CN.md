<h1 align="center">PhotoBack</h1>

<p align="center">
  一个自托管摄影活动交付平台：为每次活动创建项目，生成唯一访问链接，并让访客下载或选择照片。
</p>

<p align="center">
  <a href="README.md">English</a> &middot;
  <a href="https://photoback.rosebeg.com/view/8b6ab9d9">访客测试页面</a> &middot;
  <a href="#快速开始">快速开始</a> &middot;
  <a href="#功能">功能</a>
</p>

<p align="center">
  <a href="https://github.com/Ha22yX/PhotoBack"><img alt="GitHub repo" src="https://img.shields.io/badge/GitHub-PhotoBack-111?style=for-the-badge&logo=github" /></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-205A4B?style=for-the-badge&logo=python&logoColor=white" />
  <img alt="Flask" src="https://img.shields.io/badge/Flask-Web_App-6B7FD7?style=for-the-badge&logo=flask&logoColor=white" />
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-Local_DB-7B8C86?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img alt="Google Drive" src="https://img.shields.io/badge/Google_Drive-Optional-2B6F5B?style=for-the-badge&logo=googledrive&logoColor=white" />
</p>

<p align="center">
  <img src=".github/assets/readme-hero.svg" alt="项目概览图" />
</p>

## 项目定位

PhotoBack 来自真实摄影师工作流：活动结束后创建项目，上传修好的照片或视频，把唯一链接分享给参与者，访客就可以浏览、下载或选择自己需要的照片。

重点是基于唯一链接的交付方式。每个项目都有自己的短访问 key，项目不会公开列出，只有拿到链接的人才能访问。

## 功能

- 管理后台：创建摄影项目、填写客户信息、管理项目状态。
- 批量上传图片和视频，支持缩略图与图片优化处理。
- 访客页面 `/view/<access_link>`：浏览、预览、选择照片。
- 选中照片支持直接下载、生成分享链接、邮件发送或可选 Google Drive 交付。
- 后台可查看访客选择记录，方便摄影师后续交付。
- 公开仓库不会提交活动照片、本地数据库、SMTP 密码、Google token 等私密运行数据。

## 技术栈

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 后端 | Python, Flask | 路由、项目流程、上传、交付操作 |
| 数据 | SQLite, SQLAlchemy, Flask-Migrate | 项目、照片、选择记录和管理员用户 |
| 前端 | Jinja templates, CSS, JavaScript | 管理后台和访客图库界面 |
| 媒体处理 | Pillow, 可选 ffmpeg | 图片优化和视频缩略图 |
| 集成 | SMTP, Google Drive API | 邮件交付和可选云端分享 |

## 快速开始

```bash
git clone https://github.com/Ha22yX/PhotoBack.git
cd PhotoBack
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
flask --app run.py db upgrade
python run.py
```

创建管理员后访问 `http://localhost:5000/admin`。

这份备份代码没有公开注册入口。可以在 Flask shell 中创建第一个管理员：

```python
from app import db
from app.models import User

user = User(username="admin", email="admin@example.com")
user.set_password("change-this-password")
db.session.add(user)
db.session.commit()
```

## 配置

复制 `.env.example` 为 `.env`，然后根据部署环境修改：

| 变量 | 用途 |
| --- | --- |
| `SECRET_KEY` | Flask session 和 CSRF 签名密钥 |
| `SITE_URL` | 生成分享链接时使用的公开站点地址 |
| `DATABASE_URL` | SQLAlchemy 数据库地址，默认 SQLite |
| `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | 邮件发送配置 |
| `EMAIL_DOMAIN`, `SUPPORT_EMAIL` | 对外邮件域名和支持邮箱 |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID` | 可选 Google Drive 集成 |
| `MAX_UPLOAD_MB` | 上传请求大小限制 |

## 工作流

1. 摄影师在后台创建项目。
2. PhotoBack 为项目生成唯一访问 key。
3. 摄影师上传照片或视频。
4. 访客打开分享链接，选择图片并选择交付方式。
5. 摄影师可在后台查看选择记录，并继续发送或同步文件。

## 项目结构

```text
app/
  admin/       管理后台、上传、Google Drive 同步
  client/      访客图库、选择、下载、分享路由
  static/      CSS、JavaScript、Logo、运行时上传目录
  templates/   管理端和访客端 HTML 模板
  utils/       邮件、图片、视频和文件工具
migrations/    Flask-Migrate 数据库迁移
run.py         本地开发入口
```

## 安全说明

这个仓库已经按公开发布清理：原部署中的照片、SQLite 数据库、SMTP 密码、Google OAuth token 和 Google client secret 都不会提交到 GitHub。

唯一链接适合活动相册分享，但它不是完整的账号鉴权系统。如果用于更敏感的图库，建议再加入过期时间、访问密码或账号权限控制。

## Roadmap

- 添加首次运行的管理员创建命令。
- 添加 Docker 部署文件。
- 增加项目过期或密码保护。
- 为上传、选择、下载流程补充自动化测试。

## License

当前还没有添加 License 文件。
