from flask import Flask, render_template, request, redirect, session, abort, url_for
from database import db
from sqlalchemy import text
from tasks import TASKS
from werkzeug.utils import secure_filename
import os
import random
from datetime import datetime
import json
from html import escape
from html.parser import HTMLParser

app = Flask(__name__)
#БД
app.secret_key = '234234dsfsdf'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/upload/images'
app.config['ATTACHMENT_FOLDER'] = 'static/upload/files'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Создать папку для загрузок если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ATTACHMENT_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def find_task_variant(slug):
    for task_meta in TASKS:
        for variant in task_meta.get('variants', []):
            if variant.get('slug') == slug:
                return task_meta, variant
    return None, None


db.init_app(app)

class User(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    user_task_complite = db.Column(db.Integer,nullable=True)

    def __repr__(self):
        return f'<User {self.id}>'
class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(10), nullable=False)
    text = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(70), nullable=False)
    difficulty = db.Column(db.String(70), nullable=False)
    file_url = db.Column(db.String(500), nullable=True) 
    images = db.relationship("Images", backref="task", cascade="all, delete-orphan", lazy="selectin")

    def __repr__(self):
        return f'<Task {self.id}>'
    
    def add_images(self, files, upload_folder):
        """Автоматически добавляет изображения к задаче"""
        position = 0
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{self.id}_{position}_{datetime.now().timestamp()}_{file.filename}")
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                # Автоматически создаём запись в Images
                image = Images(task_id=self.id, image_url=f"/static/upload/images/{filename}", position=position)
                db.session.add(image)
                position += 1
        
        return position
class Images(db.Model):
    __tablename__ = "task_images"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    image_url = db.Column(db.String(500), nullable=False) 
    position = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<Images {self.id}>'

class TaskContent(db.Model):
    __tablename__ = "task_content"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True)
    data = db.Column(db.Text, nullable=False, default='{}')

class TaskFile(db.Model):
    __tablename__ = "task_files"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    task = db.relationship("Task", backref=db.backref("attachments", cascade="all, delete-orphan", lazy="selectin"))

def allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {
        'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'pdf', 'ods', 'zip'
    }

def save_attachments(task, files):
    for file in files:
        if not file or not file.filename or not allowed_attachment(file.filename):
            continue
        filename = secure_filename(f'{task.id}_{datetime.now().timestamp()}_{file.filename}')
        file.save(os.path.join(app.config['ATTACHMENT_FOLDER'], filename))
        db.session.add(TaskFile(task_id=task.id, file_url=f'/static/upload/files/{filename}', original_name=file.filename))

def get_answer_table(answer):
    try:
        data = json.loads(answer)
    except (TypeError, ValueError):
        return []
    return data.get('answer_table', []) if isinstance(data, dict) else []

class EditorHTMLParser(HTMLParser):
    allowed_tags = {'b', 'strong', 'i', 'em', 'u', 's', 'sup', 'sub', 'p', 'br', 'ul', 'ol', 'li', 'div'}

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.allowed_tags:
            self.parts.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self.parts.append('<br>')

    def handle_endtag(self, tag):
        if tag in self.allowed_tags and tag != 'br':
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        self.parts.append(escape(data))

def sanitize_editor_html(value):
    parser = EditorHTMLParser()
    parser.feed(value or '')
    parser.close()
    return ''.join(parser.parts)

with app.app_context():
    db.create_all()
#РОУТЫ
@app.context_processor
def inject_user():
    user_email = session.get('user_email')
    user = User.query.filter_by(email=user_email).first() if user_email else None
    return dict(user=user)

@app.route("/")
def home():
    return render_template('home.html', page_title='Главная', active_page='home')

@app.route("/tasks")
def tasks():
    return render_template('tasks.html', page_title='Задания', active_page='tasks', tasks=TASKS)

@app.route("/details")
def details():
    return render_template('details.html', page_title='Подробности задач', active_page='details')

@app.route("/settings")
def settings():
    return render_template('settings.html', page_title='Настройки', active_page='settings')

@app.route("/chat")
def chat():
    return render_template('chat.html', page_title='Чат', active_page='chat')

@app.route("/profile/<username>")
def profile(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        abort(404)

    task_stats = []

    return render_template('profile.html', page_title='Профиль', active_page='profile', user=user, task_stats=task_stats, tasks=TASKS)

@app.route("/learn")
def learn():
    return render_template('learn.html', page_title='Учебный раздел', active_page='learn')


@app.route('/task/variant/<variant_slug>')
def task_variant(variant_slug):
    task_meta, variant = find_task_variant(variant_slug)
    if task_meta is None or variant is None:
        abort(404)

    db_tasks = Task.query.filter(Task.task_id.startswith(f"{variant_slug}."))
    task_record = db_tasks.order_by(db.func.random()).first()

    template_name = 'task_1_detail.html' if task_meta.get('id') == 1 else 'task_detail.html'
    content = TaskContent.query.filter_by(task_id=task_record.id).first() if task_record else None
    task_content = json.loads(content.data) if content else {}
    answer_table = get_answer_table(task_record.answer) if task_record else []

    return render_template(
        template_name,
        page_title=variant.get('title', variant_slug),
        active_page='tasks',
        task_meta=task_meta,
        variant=variant,
        task_record=task_record,
        task_content=task_content,
        answer_table=answer_table,
    )

@app.route('/task/<int:task_id>')
def task_detail(task_id):
    task = Task.query.get_or_404(task_id)
    content = TaskContent.query.filter_by(task_id=task.id).first()
    task_content = json.loads(content.data) if content else {}
    answer_table = get_answer_table(task.answer)
    return render_template('task_detail.html', page_title=task.task_id, active_page='tasks', task_record=task, task_meta=None, variant=None, task_content=task_content, answer_table=answer_table)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        form_email = request.form['email']
        form_password = request.form['password']

        user = User.query.filter_by(email=form_email).first()
        if user and user.password == form_password:
            session['user_email'] = user.email
            return redirect('/')

        error = 'Неправильно указан пользователь или пароль'
        return render_template('login.html', error=error, page_title='Авторизация', active_page='login')
    return render_template('login.html', page_title='Авторизация', active_page='login')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        password_confirm = request.form['password_confirm']
        username = request.form['username']

        if password != password_confirm:
            error = 'Пароли не совпадают'
            return render_template('register.html', error=error, page_title='Регистрация', active_page='register')

        if User.query.filter_by(email=email).first():
            error = 'Пользователь с таким email уже существует'
            return render_template('register.html', error=error, page_title='Регистрация', active_page='register')

        user = User(email=email, password=password, username=username)
        db.session.add(user)
        db.session.commit()
        return redirect('/login')

    return render_template('register.html', page_title='Регистрация', active_page='register')
@app.route('/add', methods=['GET', 'POST'])
def add():
    # Проверка доступа - только для админа
    user_email = session.get('user_email')
    if user_email != '123@123':
        abort(403)
    
    message = None
    selected_task = request.form.get('task_number', request.args.get('task_number', ''))
    selected_variant = request.form.get('variant_slug', request.args.get('variant_slug', ''))
    selected_sequence_number = request.form.get('sequence_number', request.args.get('sequence_number', '1'))
    selected_difficulty = request.form.get('difficulty', request.args.get('difficulty', 'normal'))
    if request.method == 'POST':
        sequence_number = request.form.get('sequence_number', '').strip()
        text = request.form.get('text', '').strip()
        answer = request.form.get('answer', '').strip()
        difficulty = request.form.get('difficulty', '').strip()
        content_data = request.form.get('content_data', '{}')
        task_meta, variant = find_task_variant(selected_variant)
        try:
            content_object = json.loads(content_data)
        except (TypeError, ValueError):
            content_object = {}
        if not isinstance(content_object, dict):
            content_object = {}
        content_object['text_html'] = sanitize_editor_html(content_object.get('text_html', ''))
        for block in content_object.get('blocks', []):
            if block.get('type') == 'text':
                block['html'] = sanitize_editor_html(block.get('html', ''))
        content_data = json.dumps(content_object, ensure_ascii=False)

        if not task_meta or not variant or not sequence_number.isdigit() or not text or not answer or not difficulty:
            message = 'Выберите задание и вид, укажите номер записи, текст, ответ и сложность.'
        else:
            task_id = f'{selected_variant}.{int(sequence_number)}'
            task = Task(task_id=task_id, text=text, answer=answer, difficulty=difficulty)
            db.session.add(task)
            db.session.flush()
            image_count = task.add_images(request.files.getlist('images'), app.config['UPLOAD_FOLDER'])
            save_attachments(task, request.files.getlist('attachments'))
            TaskContent.query.filter_by(task_id=task.id).delete(synchronize_session=False)
            db.session.add(TaskContent(task_id=task.id, data=content_data))
            db.session.commit()
            message = f'Задание №{task_id} успешно добавлено ({image_count} изображений).'
            selected_sequence_number = str(int(sequence_number) + 1)

    tasks = Task.query.order_by(Task.id.desc()).all()
    return render_template('add.html', page_title='Добавить задачу', active_page='add', message=message, tasks=tasks, task_catalog=TASKS, selected_task=selected_task, selected_variant=selected_variant, selected_sequence_number=selected_sequence_number, selected_difficulty=selected_difficulty)

@app.post('/delete/task/<int:task_id>')
def delete_task(task_id):
    if session.get('user_email') != '123@123':
        abort(403)
    task = Task.query.get_or_404(task_id)
    for attachment in task.attachments:
        file_path = os.path.join(app.root_path, attachment.file_url.lstrip('/').replace('/', os.sep))
        if os.path.exists(file_path):
            os.remove(file_path)
    for image in task.images:
        file_path = os.path.join(app.root_path, image.image_url.lstrip('/').replace('/', os.sep))
        if os.path.exists(file_path):
            os.remove(file_path)
    TaskContent.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for(
        'add',
        task_number=request.form.get('task_number', ''),
        variant_slug=request.form.get('variant_slug', ''),
        sequence_number=request.form.get('sequence_number', '1'),
        difficulty=request.form.get('difficulty', 'normal'),
    ))

@app.route('/add/task-1', methods=['GET', 'POST'])
def add_task_1():
    user_email = session.get('user_email')
    if user_email != '123@123':
        abort(403)

    message = None
    if request.method == 'POST':
        number = request.form.get('number', '').strip()
        text_before = request.form.get('text_before', '').strip()
        text_after = request.form.get('text_after', '').strip()
        answer = request.form.get('answer', '').strip()
        difficulty = request.form.get('difficulty', '').strip()
        image = request.files.get('image')

        if not number or not text_before or not text_after or not answer or not difficulty or not image or not image.filename:
            message = 'Заполните все поля и загрузите изображение.'
        elif not allowed_file(image.filename):
            message = 'Разрешены изображения PNG, JPG, JPEG, GIF и WEBP.'
        else:
            task = Task(
                task_id=number,
                text=f'{text_before}\n[[IMAGE_0]]\n{text_after}',
                answer=answer,
                difficulty=difficulty,
            )
            db.session.add(task)
            db.session.flush()
            task.add_images([image], app.config['UPLOAD_FOLDER'])
            db.session.commit()
            message = f'Задание №{number} успешно добавлено.'

    tasks = Task.query.filter(Task.task_id.startswith('1.')).order_by(Task.id.desc()).all()
    return render_template('add_task_1.html', page_title='Добавить задание 1', active_page='add', message=message, tasks=tasks)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    
    