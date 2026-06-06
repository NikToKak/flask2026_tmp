import os
import json
import uuid
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(256)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

UPLOAD_FOLDER = 'uploads'
DATA_FILE = 'files_data.json'
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.txt', '.pdf', '.docx'}
FORBIDDEN_EXTENSIONS = {'.exe', '.sh', '.php', '.js'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_files_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_files_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_file_md5(content):
    return hashlib.md5(content).hexdigest()

def is_duplicate(md5_hash, files_data):
    return any(file['md5'] == md5_hash for file in files_data)

def get_file_extension(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext

def generate_unique_filename(original_ext):
    uid = uuid.uuid4().hex
    dir1 = uid[:2]
    dir2 = uid[2:4]
    filename = f"{uid}{original_ext}"
    relative_path = os.path.join(UPLOAD_FOLDER, dir1, dir2, filename)
    return relative_path, uid

def save_file(content, relative_path):
    full_path = os.path.join(app.root_path, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'wb') as f:
        f.write(content)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        uploaded_file = request.files.get('file')
        if not uploaded_file or uploaded_file.filename == '':
            flash('Файл не выбран.', 'danger')
            return redirect(url_for('index'))

        original_filename = uploaded_file.filename
        ext = get_file_extension(original_filename)

        if ext in FORBIDDEN_EXTENSIONS:
            flash(f'Загрузка файлов с расширением {ext} запрещена.', 'danger')
            return redirect(url_for('index'))

        content = uploaded_file.read()
        if len(content) == 0:
            flash('Файл пуст.', 'danger')
            return redirect(url_for('index'))

        md5_hash = get_file_md5(content)
        
        files_data = load_files_data()

        if is_duplicate(md5_hash, files_data):
            flash('Файл с таким содержимым уже был загружен ранее (дубликат).', 'warning')
            return redirect(url_for('index'))

        relative_path, file_uuid = generate_unique_filename(ext)

        try:
            save_file(content, relative_path)

            file_info = {
                'uuid': file_uuid,
                'original_name': original_filename,
                'path': relative_path.replace('\\', '/'),
                'upload_date': datetime.now().isoformat(),
                'extension': ext[1:],
                'md5': md5_hash
            }
            files_data.append(file_info)
            save_files_data(files_data)

            flash(f'Файл "{original_filename}" успешно загружен.', 'success')
        except Exception as e:
            flash(f'Ошибка при сохранении файла: {str(e)}', 'danger')

        return redirect(url_for('index'))

    files_data = load_files_data()
    return render_template('index.html', files=files_data)

if __name__ == '__main__':
    app.run(debug=True)