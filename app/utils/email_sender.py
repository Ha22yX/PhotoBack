import os
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import current_app
from datetime import datetime
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate, make_msgid

def get_smtp_config():
    """Read SMTP settings from Flask config or environment variables."""
    smtp_server = current_app.config.get('SMTP_SERVER') or os.getenv('SMTP_SERVER')
    smtp_port = int(current_app.config.get('SMTP_PORT') or os.getenv('SMTP_PORT', '465'))
    username = current_app.config.get('SMTP_USERNAME') or os.getenv('SMTP_USERNAME')
    password = current_app.config.get('SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD')
    if not smtp_server or not username or not password:
        raise RuntimeError('SMTP configuration is missing. Set SMTP_SERVER, SMTP_USERNAME, and SMTP_PASSWORD.')
    return smtp_server, smtp_port, username, password

def get_email_domain():
    """Return the domain used in generated Message-ID headers."""
    configured_domain = current_app.config.get('EMAIL_DOMAIN') or os.getenv('EMAIL_DOMAIN')
    if configured_domain:
        return configured_domain

    site_url = current_app.config.get('SITE_URL') or os.getenv('SITE_URL', 'localhost')
    return site_url.replace('https://', '').replace('http://', '').split('/')[0] or 'localhost'

def get_support_email():
    """Return the public support email used in outbound messages."""
    return current_app.config.get('SUPPORT_EMAIL') or os.getenv('SUPPORT_EMAIL') or current_app.config.get('ADMIN_EMAIL', 'admin@example.com')

def send_email(to_email, subject, html_body, attachments=None):
    """
    支持 HTML 格式的发送邮件函数，可带附件
    
    参数：
    to_email：收件人邮箱（字符串或列表）
    subject：邮件主题
    html_body：HTML格式的邮件正文内容
    attachments：附件列表，格式为 [(文件路径, 文件名), ...]
    """
    # 内置发件人信息
    smtp_server, smtp_port, username, password = get_smtp_config()

    print(f"准备发送邮件给: {to_email}, 主题: {subject}")
    
    # 创建邮件对象
    msg = MIMEMultipart()
    msg['From'] = username
    msg['To'] = to_email if isinstance(to_email, str) else ', '.join(to_email)
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=get_email_domain())   # 增加消息ID增强可信度

    # 添加 HTML 正文内容
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    # 添加附件
    if attachments:
        print(f"开始添加{len(attachments)}个附件")
        for file_path, file_name in attachments:
            try:
                if not os.path.exists(file_path):
                    print(f"附件文件不存在: {file_path}")
                    continue
                    
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    print(f"附件文件大小为0: {file_path}")
                    continue
                
                with open(file_path, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=file_name)
                    part['Content-Disposition'] = f'attachment; filename="{file_name}"'
                    msg.attach(part)
                print(f"附件 {file_name} 添加成功")
            except Exception as e:
                print(f"添加附件 {file_name} 失败: {str(e)}")

    try:
        print(f"连接SMTP服务器: {smtp_server}:{smtp_port}")
        # 连接SMTP服务器（SSL加密）
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        
        print(f"登录邮箱账户: {username}")
        server.login(username, password)

        # 发送邮件
        print(f"发送邮件到: {to_email}")
        server.sendmail(username, to_email, msg.as_string())

        print("✅ HTML 邮件发送成功！")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP身份验证失败: {str(e)}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        print(f"❌ 收件人被拒绝: {str(e)}")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP错误: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 邮件发送失败: {str(e)}")
        return False
    finally:
        try:
            server.quit()
        except:
            pass


def send_project_files(to_email, project_title, files, test_mode=False):
    """
    将项目文件发送到客户的邮箱，通过外链图片而非附件
    
    参数:
    - to_email: 收件人邮箱
    - project_title: 项目标题
    - files: 文件列表，格式为 [(file_path, original_filename), ...]
    - test_mode: 测试模式，如果为True，将发送到管理员邮箱而不是原始收件人
    
    返回:
    - 布尔值，表示发送成功或失败
    """
    print(f"准备发送项目 '{project_title}' 文件给 {to_email}, 文件数量: {len(files)}, 测试模式: {test_mode}")
    
    # 内置发件人信息
    smtp_server, smtp_port, username, password = get_smtp_config()
    
    if test_mode:
        # 测试模式下，将发送到管理员邮箱
        admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
        print(f"测试模式: 原收件人 {to_email}, 改为发送到管理员邮箱 {admin_email}")
        actual_recipient = admin_email
    else:
        actual_recipient = to_email
    
    # 验证邮箱格式
    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", actual_recipient):
        print(f"错误: 收件人邮箱格式不正确: {actual_recipient}")
        return False
    
    valid_files = []
    
    # 验证文件是否存在
    for file_path, original_filename in files:
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path} ({original_filename})")
            continue
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            print(f"文件大小为0: {file_path} ({original_filename})")
            continue
            
        valid_files.append((file_path, original_filename))
        print(f"有效文件: {original_filename}, 大小: {file_size/1024:.2f} KB")
    
    print(f"有效文件数量: {len(valid_files)}")
    
    if not valid_files:
        print("错误: 没有有效文件可供发送")
        return False
    
    # 准备邮件内容
    msg = MIMEMultipart('alternative')
    
    msg['From'] = username
    msg['To'] = actual_recipient
    support_email = get_support_email()
    msg['List-Unsubscribe'] = f"<mailto:{support_email}>"
    
    if test_mode:
        msg['Subject'] = f"[TEST] {project_title} - Your Selected Photos"
    else:
        msg['Subject'] = f"{project_title} - Your Selected Photos"
        
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=get_email_domain())   # 增加消息ID增强可信度

    # 构建图片预览HTML内容
    image_html = ""
    
    # 尝试从Selection中获取share_key，以生成分享链接
    share_link = None
    
    # 从第一个文件中提取项目ID，以便生成项目链接
    try:
        # 尝试从Selection中获取project对象
        from app.models import Photo, Project, Selection
        first_file_path = valid_files[0][0] if valid_files else None
        if first_file_path:
            filename = os.path.basename(first_file_path)
            # 查找对应的照片记录
            photo = Photo.query.filter_by(filename=filename).first()
            
            # 如果无法通过完整文件名找到，尝试用UUID部分查找
            if not photo:
                uuid_part = filename.split('.')[0]
                photo = Photo.query.filter(Photo.filename.startswith(uuid_part)).first()
                print(f"通过UUID部分 {uuid_part} 查找照片: {'成功' if photo else '失败'}")
            
            if photo and photo.project:
                # 获取项目的访问链接
                project_link = f"{current_app.config['SITE_URL']}/view/{photo.project.access_link}"
                print(f"找到项目: ID {photo.project.id}, 标题 '{photo.project.title}', 访问链接 '{photo.project.access_link}'")
                
                # 尝试查找最近的选择记录，获取share_key
                selection = Selection.query.filter_by(
                    project_id=photo.project.id, 
                    email=to_email
                ).order_by(Selection.submit_time.desc()).first()
                
                if selection and selection.share_key:
                    # 生成分享链接
                    share_link = f"{current_app.config['SITE_URL']}/view/{photo.project.access_link}/shared/{selection.share_key}"
                    print(f"已生成分享链接: {share_link}")
                else:
                    print("未找到有效的选择记录或share_key为空")
            else:
                project_link = current_app.config['SITE_URL']
        else:
            project_link = current_app.config['SITE_URL']
    except Exception as e:
        print(f"无法获取项目链接: {str(e)}")
        project_link = current_app.config['SITE_URL']
        share_link = None
    
    # 如果没有找到share_link，但能够获取到photo和project，则生成一个新的分享链接
    if not share_link and 'photo' in locals() and photo and photo.project:
        try:
            from app.models import Selection, SelectedPhoto, Photo
            import uuid
            from flask import session
            from app import db
            
            print(f"准备生成新的分享链接，项目ID: {photo.project.id}, 邮箱: {to_email}")
            
            # 复制自generate_share_link函数的核心逻辑
            # 创建一个新的选择记录，或使用现有的
            selection = Selection.query.filter_by(
                project_id=photo.project.id, 
                email=to_email,
                delivery_method='link'
            ).first()
            
            if selection:
                print(f"使用现有选择记录 ID: {selection.id}, 照片数: {len(selection.selected_photos) if selection.selected_photos else 0}")
                # 如果已经有share_key，保存它用于后续比较
                existing_share_key = selection.share_key
            else:
                print(f"没有找到现有选择记录，将创建新记录")
                existing_share_key = None
            
            # 如果没有现有记录或者现有记录里没有照片，则创建新记录
            if not selection or not selection.selected_photos:
                if not selection:
                    selection = Selection(
                        project_id=photo.project.id,
                        email=to_email,
                        delivery_method='link'
                    )
                    db.session.add(selection)
                    db.session.commit()
                    print(f"已创建新选择记录 ID: {selection.id}")
                else:
                    print(f"现有选择记录 ID: {selection.id} 没有照片，将重新添加")
            
            # 添加所有有效照片到Selection记录
            photo_count = 0
            for filepath, original_filename in valid_files:
                try:
                    filename = os.path.basename(filepath)
                    # 尝试用完整文件名查询
                    file_photo = Photo.query.filter_by(filename=filename).first()
                    
                    # 如果找不到，尝试只用UUID部分查询
                    if not file_photo:
                        uuid_part = filename.split('.')[0]
                        file_photo = Photo.query.filter(Photo.filename.startswith(uuid_part)).first()
                        print(f"尝试使用UUID部分 {uuid_part} 查找照片: {'成功' if file_photo else '失败'}")
                    
                    # 如果仍然找不到，尝试通过原始文件名查找
                    if not file_photo:
                        file_photo = Photo.query.filter_by(original_filename=original_filename).filter_by(project_id=photo.project.id).first()
                        print(f"尝试通过原始文件名 {original_filename} 查找照片: {'成功' if file_photo else '失败'}")
                    
                    if file_photo:
                        # 确保照片属于同一个项目
                        if file_photo.project_id == photo.project.id:
                            # 检查这个照片是否已经添加到选择中
                            existing = db.session.query(SelectedPhoto).filter_by(
                                selection_id=selection.id, 
                                photo_id=file_photo.id
                            ).first()
                            
                            if not existing:
                                selected_photo = SelectedPhoto(selection_id=selection.id, photo_id=file_photo.id)
                                db.session.add(selected_photo)
                                photo_count += 1
                                print(f"添加照片 {file_photo.id} (文件名: {file_photo.filename}) 到选择 {selection.id}")
                            else:
                                print(f"照片 {file_photo.id} 已经添加到选择中，跳过")
                        else:
                            print(f"警告: 照片 {file_photo.id} 属于不同的项目 ({file_photo.project_id} vs {photo.project.id})")
                    else:
                        print(f"错误: 无法在数据库中找到照片文件 {filename} (原始文件名: {original_filename})")
                except Exception as e:
                    print(f"添加照片到选择时出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            if photo_count == 0:
                print("警告: 没有任何照片被添加到选择记录中!")
                # 如果我们在邮件中只有一张照片，而且可能是当前查询到的照片，就直接添加它
                if 'photo' in locals() and photo:
                    try:
                        # 检查这个照片是否已经添加到选择中
                        existing = db.session.query(SelectedPhoto).filter_by(
                            selection_id=selection.id, 
                            photo_id=photo.id
                        ).first()
                        
                        if not existing:
                            selected_photo = SelectedPhoto(selection_id=selection.id, photo_id=photo.id)
                            db.session.add(selected_photo)
                            print(f"已添加当前照片 {photo.id} 到选择")
                            photo_count = 1
                        else:
                            print(f"当前照片 {photo.id} 已经添加到选择中")
                    except Exception as e:
                        print(f"添加当前照片时出错: {str(e)}")
                        import traceback
                        traceback.print_exc()
            
            print(f"总计添加了 {photo_count} 张照片到选择 {selection.id}")
            db.session.commit()
            print(f"数据库事务已提交")
            
            # 生成唯一的分享密钥（完全匹配routes.py中的实现）
            # 只有在没有share_key或者share_key为空时才生成新的
            if not selection.share_key:
                print(f"选择记录没有share_key，将生成新的")
                # 与routes.py中完全相同的逻辑
                selection.share_key = uuid.uuid4().hex[:12]
                db.session.commit()
                print(f"已生成新的share_key: {selection.share_key}")
            else:
                print(f"使用现有share_key: {selection.share_key}")
            
            # 检查share_key是否发生变化
            if existing_share_key and existing_share_key != selection.share_key:
                print(f"警告: share_key已更改 ({existing_share_key} -> {selection.share_key})")
            
            # 使用完全相同的分享链接格式
            share_link = f"{current_app.config['SITE_URL']}/view/{photo.project.access_link}/shared/{selection.share_key}"
            
            # 保存分享链接到会话，与routes.py中一致
            session['share_link'] = share_link
            
            print(f"已创建新的分享链接: {share_link}")
            
            # 额外检查：验证选择记录中确实有照片
            select_photo_count = db.session.query(SelectedPhoto).filter_by(selection_id=selection.id).count()
            if select_photo_count == 0:
                print(f"严重警告: 选择记录 {selection.id} 中没有照片！")
            else:
                print(f"选择记录 {selection.id} 包含 {select_photo_count} 张照片，链接应该有效")
        except Exception as e:
            print(f"创建分享链接时出错: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印完整的错误堆栈信息
            share_link = None
    
    for i, (file_path, original_filename) in enumerate(valid_files):
        # 从文件路径中提取UUID (假设文件名格式为UUID.扩展名)
        uuid = os.path.basename(file_path).split('.')[0]
        # 创建图片外链URL - 使用完整的绝对URL
        base_url = current_app.config.get('SITE_URL', 'http://localhost:5000')
        # 确保base_url不以斜杠结尾
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        # 修正图片URL路径，使用正确的route路径
        image_url = f"{base_url}/image/{uuid}"
        
        # 从数据库中获取文件类型信息
        try:
            from app.models import Photo
            filename = os.path.basename(file_path)
            photo = Photo.query.filter_by(filename=filename).first()
            is_video = photo is not None and photo.file_type == 'video'
        except Exception as e:
            print(f"获取文件类型失败: {str(e)}")
            # 回退到扩展名判断
            file_ext = os.path.basename(file_path).split('.')[-1].lower()
            is_video = file_ext in ['mp4', 'mov']
        
        # 为每个媒体文件创建一个预览卡片
        image_html += f"""
        <div style="margin-bottom: 25px; background: #1a1a3a; border-radius: 8px; padding: 15px; text-align: center;">
            {f'<video src="{image_url}" controls preload="metadata" style="max-width: 100%; border-radius: 6px;"></video>' if is_video else f'<img src="{image_url}" alt="{original_filename}" style="max-width: 100%; border-radius: 6px;">'}
            <p style="margin: 10px 0; color: #7a7aa9; font-size: 14px;">{original_filename}</p>
            <a href="{image_url}" target="_blank" style="display: inline-block; padding: 8px 15px; font-size: 14px; background: linear-gradient(90deg, #00e3ff, #ff00c8); color: #0b0b2d; border-radius: 6px; text-decoration: none; font-weight: bold;">View Original</a>
        </div>
        """
    
    # 创建纯文本版本
    view_link = share_link if share_link else project_link
    plain_text = f"""\
Hello,

Thank you for viewing Rosebeg Studio photography work.

You can view the photos of your choice here: {view_link}

Rosebeg Studio · Capturing Life's Beauty
"""
    
    # 添加纯文本版本
    msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))
    
    # 创建HTML内容
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <title>Your Photos Are Ready</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #0b0b2d; color: #ffffff;">
    <div style="max-width: 600px; margin: 30px auto; background: #14142b; border-radius: 12px; padding: 40px; text-align: center;">
        
        <!-- logo -->
        <img src="{base_url}/rosebeglogo" alt="Studio Logo" style="max-width: 150px; margin-bottom: 20px; border-radius: 12px;">

        <!-- title -->
        <h2 style="font-size: 24px; margin-bottom: 10px;">Your Photos Are Ready</h2>

        <!-- intro -->
        <p style="font-size: 16px; color: #d1d1e9; margin-bottom: 30px;">
        Hello,<br><br>
        Thank you for viewing <strong>Rosebeg Studio</strong> photography work.<br><br>
        Your selected photos are displayed below:
        </p>

        <!-- image preview -->
        <div style="margin: 30px 0;">
        {image_html}
        </div>
        
        <!-- share link (if available) -->
        {f'''
        <div style="margin: 30px 0; background: #1a1a3a; border-radius: 8px; padding: 20px; text-align: center;">
            <h3 style="font-size: 18px; margin-bottom: 15px; color: #ffffff;">🔗 Share Link</h3>
            <p style="font-size: 16px; color: #d1d1e9; margin-bottom: 15px;">
                You can also share your selected photos using this link:
            </p>
            <a href="{share_link}" target="_blank" style="display: block; padding: 12px; background: #2a2a4a; color: #ffffff; border-radius: 6px; text-decoration: none; font-family: monospace; word-break: break-all; margin-bottom: 15px;">
                {share_link}
            </a>
            <p style="font-size: 14px; color: #7a7aa9; margin: 0;">
                This link will remain valid indefinitely. Keep it safe and only share with people you trust.
            </p>
        </div>
        ''' if share_link else ''}

        <!-- button -->
        <a href="{project_link}" target="_blank" style="display: inline-block; padding: 12px 30px; font-size: 16px; font-weight: bold; background: linear-gradient(90deg, #00e3ff, #ff00c8); color: #0b0b2d; border-radius: 8px; text-decoration: none;">
        Return to Gallery
        </a>

        <!-- footer -->
        <p style="margin-top: 40px; font-size: 13px; color: #7a7aa9;">
        Rosebeg Studio · Capturing Life's Beauty<br>
        If you received this in error, or wish to stop receiving emails from us, please contact <a href="mailto:{support_email}" style="color: #7a7aa9; text-decoration: underline;">{support_email}</a>.
        </p>

    </div>
    </body>
    </html>
    """
    
    # 添加 HTML 正文内容
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    try:
        print(f"连接SMTP服务器: {smtp_server}:{smtp_port}")
        # 连接SMTP服务器（SSL加密）
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        
        print(f"登录邮箱账户: {username}")
        server.login(username, password)

        # 发送邮件
        print(f"发送邮件到: {actual_recipient}")
        server.sendmail(username, actual_recipient, msg.as_string())

        print("✅ HTML 邮件发送成功！")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP身份验证失败: {str(e)}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        print(f"❌ 收件人被拒绝: {str(e)}")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP错误: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 邮件发送失败: {str(e)}")
        return False
    finally:
        try:
            server.quit()
        except:
            pass 
