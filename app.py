import os
from flask import Flask, render_template, redirect, url_for, flash, request, send_file, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config
from models import db, User, History
from forms import RegistrationForm, LoginForm, UploadForm
from utils import process_python_to_c
from datetime import datetime
import uuid

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password_hash=generate_password_hash('Admin1234!')
        )
        db.session.add(admin)
        db.session.commit()
        print('Admin user created.')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed = generate_password_hash(form.password.data)
        user = User(username=form.username.data, password_hash=hashed)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    form = UploadForm()
    return render_template('index.html', form=form)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        file = form.file.data
        if file and file.filename.endswith('.txt'):
            original_filename = secure_filename(file.filename)
            source_code = file.read().decode('utf-8')
            result_code = process_python_to_c(source_code)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            result_filename = f"result_{current_user.id}_{timestamp}_{uuid.uuid4().hex[:8]}.txt"
            result_path = os.path.join(app.config['RESULT_FOLDER'], result_filename)
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write(result_code)
            preview = result_code[:200] + ('...' if len(result_code) > 200 else '')
            history = History(
                user_id=current_user.id,
                original_filename=original_filename,
                result_filename=result_filename,
                result_preview=preview
            )
            db.session.add(history)
            db.session.commit()
            flash('File processed successfully.', 'success')
            return redirect(url_for('result', history_id=history.id))
        else:
            flash('Please upload a .txt file.', 'danger')
    return redirect(url_for('index'))

@app.route('/result/<int:history_id>')
@login_required
def result(history_id):
    history = History.query.get_or_404(history_id)
    if history.user_id != current_user.id:
        abort(403)
    result_path = os.path.join(app.config['RESULT_FOLDER'], history.result_filename)
    if not os.path.exists(result_path):
        abort(404)
    with open(result_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return render_template('result.html', history=history, content=content)

@app.route('/download/<filename>')
@login_required
def download(filename):
    # Проверяем, принадлежит ли файл текущему пользователю
    history = History.query.filter_by(result_filename=filename).first()
    if not history or history.user_id != current_user.id:
        abort(403)
    filepath = os.path.join(app.config['RESULT_FOLDER'], filename)
    if not os.path.exists(filepath):
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/history')
@login_required
def history():
    user_histories = History.query.filter_by(user_id=current_user.id).order_by(History.created_at.desc()).all()
    return render_template('history.html', histories=user_histories)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
    app.run(debug=True)