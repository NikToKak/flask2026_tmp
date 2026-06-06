from flask import Flask, render_template, redirect, url_for, request, session, flash, send_file
from models import db, User, Post, Category, Tag, post_tags
from forms import LoginForm, RegisterForm, PostForm, CategoryForm, TagForm
from flask_wtf.csrf import CSRFProtect
import os
import json
from datetime import datetime
from sqlalchemy import or_

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
csrf = CSRFProtect(app)

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Создан admin / admin123')
            for cat_name in ['Новости', 'Статьи', 'Обзоры']:
                if not Category.query.filter_by(name=cat_name).first():
                    db.session.add(Category(name=cat_name))
            db.session.commit()

@app.template_filter('datetime')
def format_datetime(value):
    if value:
        return value.strftime('%d.%m.%Y %H:%M')
    return ''

# АВТОРИЗАЦИЯ
@app.route('/login', methods=['GET','POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Вы вошли', 'success')
            return redirect(url_for('index'))
        flash('Неверные данные', 'danger')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET','POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('index'))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Имя занято', 'danger')
        else:
            user = User(username=form.username.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна, войдите', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли', 'info')
    return redirect(url_for('index'))

# ГЛАВНАЯ - СПИСОК ПОСТОВ С ФИЛЬТРАМИ
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    author_id = request.args.get('author', type=int)
    tag_id = request.args.get('tag', type=int)

    query = Post.query

    if not session.get('user_id'):
        query = query.filter(Post.is_private == False)

    if category_id:
        query = query.filter(Post.category_id == category_id)
    if author_id:
        query = query.filter(Post.user_id == author_id)
    if tag_id:
        query = query.join(post_tags).filter(post_tags.c.tag_id == tag_id)

    posts = query.order_by(Post.created_at.desc()).paginate(page=page, per_page=5)
    categories = Category.query.all()
    tags = Tag.query.all()
    users = User.query.all()

    return render_template('index.html', posts=posts, categories=categories, tags=tags, users=users,
                           selected_category=category_id, selected_author=author_id, selected_tag=tag_id)

# CRUD ПОСТОВ
@app.route('/post/new', methods=['GET','POST'])
def post_create():
    if not session.get('user_id'):
        flash('Авторизуйтесь', 'warning')
        return redirect(url_for('login'))
    form = PostForm()
    form.category_id.choices = [(0, '-- Выберите --')] + [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        tags_str = form.tags.data.strip()
        tag_objects = []
        if tags_str:
            for tag_name in tags_str.split(','):
                tag_name = tag_name.strip()
                if tag_name:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                    tag_objects.append(tag)
        post = Post(
            title=form.title.data,
            content=form.content.data,
            is_private=form.is_private.data,
            user_id=session['user_id'],
            category_id=form.category_id.data if form.category_id.data != 0 else None
        )
        db.session.add(post)
        db.session.commit()
        post.tags = tag_objects
        db.session.commit()
        flash('Пост создан', 'success')
        return redirect(url_for('index'))
    return render_template('post_form.html', form=form, title='Новый пост')

@app.route('/post/<int:id>/edit', methods=['GET','POST'])
def post_edit(id):
    if not session.get('user_id'):
        flash('Авторизуйтесь', 'warning')
        return redirect(url_for('login'))
    post = Post.query.get_or_404(id)
    if post.user_id != session['user_id']:
        flash('Вы не автор', 'danger')
        return redirect(url_for('index'))
    form = PostForm(obj=post)
    form.category_id.choices = [(0, '-- Без категории --')] + [(c.id, c.name) for c in Category.query.all()]
    if request.method == 'GET':
        form.tags.data = ', '.join([t.name for t in post.tags])
        if post.category_id:
            form.category_id.data = post.category_id
        else:
            form.category_id.data = 0
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        post.is_private = form.is_private.data
        post.category_id = form.category_id.data if form.category_id.data != 0 else None
        tags_str = form.tags.data.strip()
        new_tags = []
        if tags_str:
            for tag_name in tags_str.split(','):
                tag_name = tag_name.strip()
                if tag_name:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                    new_tags.append(tag)
        post.tags = new_tags
        db.session.commit()
        flash('Пост обновлён', 'success')
        return redirect(url_for('index'))
    return render_template('post_form.html', form=form, title='Редактирование')

@app.route('/post/<int:id>/delete', methods=['POST'])
def post_delete(id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    post = Post.query.get_or_404(id)
    if post.user_id != session['user_id']:
        flash('Нельзя удалить чужой пост', 'danger')
        return redirect(url_for('index'))
    db.session.delete(post)
    db.session.commit()
    flash('Пост удалён', 'success')
    return redirect(url_for('index'))

# УПРАВЛЕНИЕ КАТЕГОРИЯМИ
@app.route('/categories')
def categories_list():
    if not session.get('user_id'):
        flash('Авторизуйтесь', 'warning')
        return redirect(url_for('login'))
    cats = Category.query.all()
    return render_template('categories.html', categories=cats)

@app.route('/category/new', methods=['GET','POST'])
def category_create():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    form = CategoryForm()
    if form.validate_on_submit():
        if Category.query.filter_by(name=form.name.data).first():
            flash('Категория уже есть', 'danger')
        else:
            cat = Category(name=form.name.data)
            db.session.add(cat)
            db.session.commit()
            flash('Категория создана', 'success')
            return redirect(url_for('categories_list'))
    return render_template('category_form.html', form=form)

@app.route('/category/<int:id>/delete', methods=['POST'])
def category_delete(id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    cat = Category.query.get_or_404(id)
    for post in cat.posts:
        post.category_id = None
    db.session.delete(cat)
    db.session.commit()
    flash('Категория удалена', 'success')
    return redirect(url_for('categories_list'))

# УПРАВЛЕНИЕ ТЕГАМИ
@app.route('/tags')
def tags_list():
    if not session.get('user_id'):
        flash('Авторизуйтесь', 'warning')
        return redirect(url_for('login'))
    tags = Tag.query.all()
    return render_template('tags.html', tags=tags)

@app.route('/tag/new', methods=['GET','POST'])
def tag_create():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    form = TagForm()
    if form.validate_on_submit():
        if Tag.query.filter_by(name=form.name.data).first():
            flash('Тег уже есть', 'danger')
        else:
            tag = Tag(name=form.name.data)
            db.session.add(tag)
            db.session.commit()
            flash('Тег создан', 'success')
            return redirect(url_for('tags_list'))
    return render_template('tag_form.html', form=form)

@app.route('/tag/<int:id>/delete', methods=['POST'])
def tag_delete(id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    tag = Tag.query.get_or_404(id)
    db.session.delete(tag)
    db.session.commit()
    flash('Тег удалён', 'success')
    return redirect(url_for('tags_list'))

# ДАМП И ИМПОРТ
@app.route('/dump')
def dump_posts():
    if not session.get('user_id'):
        flash('Авторизуйтесь', 'warning')
        return redirect(url_for('login'))
    posts = Post.query.all()
    dump_data = []
    for p in posts:
        dump_data.append({
            'id': p.id,
            'title': p.title,
            'content': p.content,
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'is_private': p.is_private,
            'author_username': p.author.username,
            'category_name': p.category.name if p.category else None,
            'tags': [t.name for t in p.tags]
        })
    with open('dump.json', 'w', encoding='utf-8') as f:
        json.dump(dump_data, f, ensure_ascii=False, indent=2)
    return send_file('dump.json', as_attachment=True, download_name='blog_dump.json')

@app.route('/import', methods=['POST'])
def import_dump():
    if not session.get('user_id'):
        flash('Авторизуйтесь', 'warning')
        return redirect(url_for('login'))
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('index'))
    if file:
        try:
            data = json.load(file)
            for item in data:
                author = User.query.filter_by(username=item['author_username']).first()
                if not author:
                    author = User(username=item['author_username'])
                    author.set_password('changeme')
                    db.session.add(author)
                    db.session.commit()
                category = None
                if item['category_name']:
                    category = Category.query.filter_by(name=item['category_name']).first()
                    if not category:
                        category = Category(name=item['category_name'])
                        db.session.add(category)
                        db.session.commit()
                post = Post(
                    title=item['title'],
                    content=item['content'],
                    created_at=datetime.fromisoformat(item['created_at']) if item['created_at'] else None,
                    is_private=item['is_private'],
                    user_id=author.id,
                    category_id=category.id if category else None
                )
                db.session.add(post)
                db.session.commit()
                for tag_name in item['tags']:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                        db.session.commit()
                    if tag not in post.tags:
                        post.tags.append(tag)
                db.session.commit()
            flash('Импорт завершён', 'success')
        except Exception as e:
            flash(f'Ошибка импорта: {e}', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8080)