from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    session,
    flash,
)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError, EqualTo
import hashlib  # вместо werkzeug.security
import os
import json
from datetime import datetime
import string
import uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(256)

def generate_password_hash(password):
    return hashlib.md5(password.encode()).hexdigest()
def check_password_hash(stored_hash, password):
    return stored_hash == hashlib.md5(password.encode()).hexdigest()

def load_json(folder_name, file_name):
    if not os.path.exists(folder_name):
        os.mkdir(folder_name)
    filename = os.path.join(folder_name, file_name)
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump(dict(), f, ensure_ascii=True)
    with open(filename, encoding="utf-8") as f:
        load_dct = json.load(f)
    return load_dct

def save_json(folder_name, file_name, save_dct):
    if not os.path.exists(folder_name):
        os.mkdir(folder_name)
    filename = os.path.join(folder_name, file_name)
    with open(filename, "w") as f:
        json.dump(save_dct, f, ensure_ascii=False, indent=4)

class RegistrationForm(FlaskForm):
    def validate_password(self, field):
        password = field.data
        if len(password) < 4:
            raise ValidationError("Пароль должен быть длиной не менее 4 символов.")

    def validate_username(self, field):
        username = field.data
        user_dct = load_json("data", "users.json")
        for user in user_dct.values():
            if username == user.get('username'):
                raise ValidationError("Такой пользователь уже зарегистрирован.")
    username = StringField("Имя пользователя",
                           validators=[
                               DataRequired(),
                               Length(min=4, max=25, message="Имя должно быть от 4 до 25 символов."),
                               validate_username
                           ])
    password = PasswordField("Пароль",
                             validators=[
                                 DataRequired(),
                                 validate_password
                             ])
    confirm = PasswordField("Повтор пароля",
                            validators=[
                                DataRequired(),
                                EqualTo("password", message="Пароли должны совпадать.")
                            ])
    submit = SubmitField("Создать пользователя")


class LoginForm(FlaskForm):
    username = StringField("Имя пользователя", validators=[DataRequired()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    submit = SubmitField("Войти")

@app.route("/")
def index():
    if session.get('logged_in'):
        return redirect(url_for('register'))
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get('logged_in'):
        return redirect(url_for('register'))
    form = LoginForm()
    if request.method == "POST" and form.validate_on_submit():        
        username = form.username.data
        password = form.password.data
        user_dct = load_json("data", "users.json")
        for user_id, user in user_dct.items():
            if user.get('username') == username:
                if check_password_hash(user.get('password'), password):
                    session['logged_in'] = True
                    session['username'] = username
                    session['user_id'] = user_id
                    user['last_login'] = datetime.now().isoformat()
                    save_json("data", "users.json", user_dct)
                    flash(f"Здравствуйте, дорогой гость {username}!", "success")
                    return redirect(url_for('register'))
                else:
                    flash("Ваш пароль неверный", "danger")
                    return render_template("login.html", form=form)
        flash("Пользователь не найден", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for('login'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if not session.get('logged_in'):
        flash("Вам необходимо авторизоваться", "warning")
        return redirect(url_for('login'))

    form = RegistrationForm()
    user_dct = load_json("data", "users.json")

    if request.method == "POST" and form.validate_on_submit():
        user_id = str(uuid.uuid4())
        hashed_password = generate_password_hash(form.password.data)

        new_user = {
            "username": form.username.data,
            "password": hashed_password,
            "registered_at": datetime.now().isoformat(),
            "last_login": None
        }
        user_dct[user_id] = new_user
        save_json("data", "users.json", user_dct)

        flash(f"Пользователь {form.username.data} был успешно создан!", "success")
        return redirect(url_for('register'))

    return render_template("register.html", form=form, users=user_dct)


if __name__ == "__main__":
    if not os.path.exists("data"):
        os.mkdir("data")

    users_file = "data/users.json"
    if not os.path.exists(users_file) or os.path.getsize(users_file) == 0:
        admin_id = str(uuid.uuid4())
        default_user = {
            admin_id: {
                "username": "admin",
                "password": generate_password_hash("Admin1234567890!"),
                "registered_at": datetime.now().isoformat(),
                "last_login": None
            }
        }
        save_json("data", "users.json", default_user)
        print("Создан пользователь admin с паролем Admin1234567890!")

    app.run(debug=True, port=8080)