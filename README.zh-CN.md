<h1 align="center">PhotoBack</h1>

<p align="center">
  一个自托管摄影交付平台，用于活动图库、唯一链接分享、客户选片和 Google Drive 双重备份。
</p>

<p align="center">
  <a href="README.md">English</a> &middot;
  <a href="https://photoback.rosebeg.com/view/8b6ab9d9">访客测试页面</a> &middot;
  <a href="#项目预览">项目预览</a> &middot;
  <a href="#快速开始">快速开始</a> &middot;
  <a href="#google-drive-备份机制">Google Drive 备份</a>
</p>

<p align="center">
  <a href="https://github.com/Ha22yX/PhotoBack"><img alt="GitHub repo" src="https://img.shields.io/badge/GitHub-PhotoBack-111?style=for-the-badge&logo=github" /></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-205A4B?style=for-the-badge&logo=python&logoColor=white" />
  <img alt="Flask" src="https://img.shields.io/badge/Flask-Web_App-6B7FD7?style=for-the-badge&logo=flask&logoColor=white" />
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-Local_DB-7B8C86?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img alt="Google Drive" src="https://img.shields.io/badge/Google_Drive-Backup-2B6F5B?style=for-the-badge&logo=googledrive&logoColor=white" />
  <img alt="License" src="https://img.shields.io/badge/License-MIT-8A6F48?style=for-the-badge" />
</p>

<p align="center">
  <img src=".github/assets/readme-hero.svg" alt="项目概览图" />
</p>

## 项目预览

<table>
  <tr>
    <td>
      <img src=".github/assets/photoback-admin-sync.png" alt="PhotoBack 后台项目页，包含上传区、分享链接、图库和 Google Drive 同步状态" />
    </td>
  </tr>
  <tr>
    <td><strong>摄影师后台。</strong> 创建活动项目、上传照片/视频、复制访客链接，并在同一个页面确认 Google Drive 同步状态。</td>
  </tr>
</table>

<table>
  <tr>
    <td width="50%">
      <img src=".github/assets/photoback-visitor-gallery.png" alt="PhotoBack 访客图库页面，可通过唯一链接选择喜欢的照片" />
    </td>
    <td width="50%">
      <img src=".github/assets/photoback-delivery-flow.png" alt="PhotoBack 交付页面，可将选中照片打包下载" />
    </td>
  </tr>
  <tr>
    <td><strong>访客图库。</strong> 访客打开唯一项目链接，浏览并选择自己喜欢的照片。</td>
    <td><strong>交付流程。</strong> 选中的照片可以下载、邮件发送、生成分享链接，或通过 Google Drive 交付。</td>
  </tr>
</table>

## 项目定位

PhotoBack 来自真实摄影师工作流：活动结束后创建项目，上传修好的照片或视频，把一个干净的链接发给参与者，让他们自己选择或下载需要的照片。

这个项目不是通用网盘相册，而是一个摄影师自托管交付台：你可以控制自己的网站、本地文件、客户链接和可选的云端备份。

## 功能

- 基于项目的图库，每个项目生成类似 `/view/<access_link>` 的唯一访问链接。
- 管理后台支持项目状态、客户信息、上传、选择记录、清理和 Drive 同步。
- 支持图片和视频批量上传，自动生成缩略图，并对图片做优化处理。
- 访客端支持浏览、预览、选片、确认选择和选择交付方式。
- 交付方式包括 ZIP 下载、邮件发送、生成分享链接和 Google Drive 合集。
- Google Drive 备份流程：项目文件夹、照片 Drive ID、手动全量同步和同步状态显示。
- 公开仓库会忽略运行时上传、本地 SQLite 数据库、OAuth token、SMTP 密钥和本地实例配置。

## 技术栈

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 后端 | Python, Flask | 项目流程、路由、上传、管理端和访客端页面 |
| 数据 | SQLite, SQLAlchemy, Flask-Migrate | 项目、照片、选择记录、Drive ID 和管理员用户 |
| 前端 | Jinja templates, CSS, JavaScript | 管理后台、图库网格、选片和交付界面 |
| 媒体处理 | Pillow, 可选 ffmpeg | 图片优化、缩略图和视频预览帧 |
| 交付 | SMTP, ZIP generation, Google Drive API | 邮件交付、下载、分享链接和云端交付 |

## Google Drive 备份机制

配置 Google Drive 后，PhotoBack 会为项目媒体保留两份副本：

1. 原始本地上传先保存到配置的上传目录，并写入 SQLite。
2. 创建项目时会尝试创建或找到对应的 Google Drive 项目文件夹。
3. 每次本地上传成功后，PhotoBack 会调用 `sync_photo_upload(photo)` 上传到 Drive 文件夹，并记录返回的 `drive_file_id`。
4. 管理后台也提供 `Sync to Google Drive` 手动按钮，可对已有照片执行全量同步。
5. 如果 Drive 同步失败，本地上传仍然保留，界面会返回 warning，而不是丢失已经上传的文件。

所以 Google Drive 在这里是备份和分享层，而不是唯一存储层。部署时请把 OAuth token 放在 Git 之外的本地实例目录。

## 快速开始

```bash
git clone https://github.com/Ha22yX/PhotoBack.git
cd PhotoBack
python -m venv .venv

# Windows PowerShell
.venv\Scripts\activate

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
flask --app run.py db upgrade
python run.py
```

创建管理员后访问 `http://localhost:5000/admin`。

这份备份代码没有公开注册入口。可以在 Flask shell 中创建第一个管理员：

```bash
flask --app run.py shell
```

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
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_PROJECT_ID` | 可选 Google Drive OAuth 应用配置 |
| `MAX_UPLOAD_MB` | 上传请求大小限制 |

如果启用 Google Drive 同步，请把生成的 OAuth token 放在版本控制之外，推荐使用 `instance/google_token.json`。仓库会主动忽略 token 文件。

## 工作流

1. 摄影师在后台创建项目。
2. PhotoBack 为项目生成唯一访问 key。
3. 摄影师上传照片或视频。
4. 如果配置了 Drive，上传内容会同步备份到对应的 Google Drive 文件夹。
5. 访客打开分享链接，选择图片并选择交付方式。
6. 摄影师可在后台查看选择记录，并继续发送、下载或同步项目文件。

## 项目结构

```text
app/
  admin/       管理后台、上传、清理、Google Drive 同步
  client/      访客图库、选择、下载、分享、Drive 交付路由
  static/      CSS、JavaScript、Logo、运行时上传目录
  templates/   管理端和访客端 HTML 模板
  utils/       邮件、图片、视频和文件工具
migrations/    Flask-Migrate 数据库迁移
run.py         本地开发入口
```

## 安全说明

唯一链接适合活动相册交付，但它不等同于账号级鉴权。如果用于更敏感的图库，建议加入过期时间、访问密码或账号权限控制。

这个公开仓库已经按发布用途清理：运行时照片、SQLite 数据库、SMTP 密码、Google OAuth token 和本地实例配置都不会提交到 GitHub。

## Roadmap

- 添加首次运行的管理员创建命令。
- 添加 Docker 部署文件。
- 增加项目过期或密码保护。
- 为上传、选片、Drive 同步和下载流程补充自动化测试。

## License

MIT License。允许商用、修改、分发和私有使用。
