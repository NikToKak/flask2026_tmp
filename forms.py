from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SelectField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Length, ValidationError
from models import Category, Tag

class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')

class RegisterForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Зарегистрироваться')

class PostForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Содержание', validators=[DataRequired()])
    is_private = BooleanField('Приватная запись (видна только авторизованным)')
    category_id = SelectField('Категория', coerce=int, validators=[DataRequired()])
    tags = StringField('Теги (через запятую)', description='Например: python, flask, sqlalchemy')
    submit = SubmitField('Сохранить')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id.choices = [(0, '-- Выберите категорию --')] + [(c.id, c.name) for c in Category.query.all()]

class CategoryForm(FlaskForm):
    name = StringField('Название категории', validators=[DataRequired(), Length(max=50)])
    submit = SubmitField('Создать')

class TagForm(FlaskForm):
    name = StringField('Название тега', validators=[DataRequired(), Length(max=50)])
    submit = SubmitField('Создать')