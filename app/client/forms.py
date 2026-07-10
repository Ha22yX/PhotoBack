from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, RadioField
from wtforms.validators import DataRequired, Email, ValidationError

class SelectionForm(FlaskForm):
    """访客选择照片表单"""
    # 使用统一标签'Download Photos'，在页面上根据照片数量动态调整显示
    delivery_method = RadioField('Delivery Method', 
                               choices=[('download', 'Download Photos'), 
                                       ('email', 'Send via Email'),
                                       ('link', 'Get Shareable Link'),
                                       ('google_drive', 'Google Drive')],
                               default='download',
                               validators=[DataRequired()])
    email = StringField('Email Address', validators=[])
    submit = SubmitField('Get My Photos')
    
    def validate_email(self, field):
        """验证邮箱字段：如果选择email方式，则邮箱必填"""
        if self.delivery_method.data == 'email' and not field.data:
            raise ValidationError('Email address is required when sending via email.')
        elif self.delivery_method.data == 'email' and field.data:
            # 验证邮箱格式
            email_validator = Email()
            email_validator(self, field) 