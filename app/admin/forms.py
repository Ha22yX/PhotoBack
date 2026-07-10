from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField, DateField
from wtforms.validators import DataRequired, Length, Email, ValidationError, Optional
from app.models import User

class LoginForm(FlaskForm):
    """管理员登录表单"""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class ProjectForm(FlaskForm):
    """项目创建表单"""
    title = StringField('Project Title', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Description')
    status = SelectField('Status', choices=[
        ('active', 'Active'), 
        ('completed', 'Completed'), 
        ('archived', 'Archived')
    ], default='active')
    deadline = DateField('Deadline', format='%Y-%m-%d', validators=[Optional()])
    client_name = StringField('Client Name', validators=[Optional(), Length(max=100)])
    client_email = StringField('Client Email', validators=[Optional(), Email()])
    submit = SubmitField('Save Project')

class RegistrationForm(FlaskForm):
    """管理员注册表单"""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired()])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.') 