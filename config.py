from datetime import timedelta
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-fallback-secret-key-taskops'

    # Session persistence (30 days for mobile PWA workers)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)

    # Database Configuration
    db_path = os.environ.get('DATABASE_PATH') or 'sqlite:///task_management.db'
    if db_path.startswith('sqlite:///') and not db_path.startswith('sqlite:////'):
        # Relative SQLite path: resolve inside instance folder
        filename = db_path.replace('sqlite:///', '')
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'instance', filename)}"
    else:
        SQLALCHEMY_DATABASE_URI = db_path

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Server & Port Binding
    GUNICORN_BIND = os.environ.get('GUNICORN_BIND', '127.0.0.1:5000')

    # Initial Admin from .env
    INITIAL_ADMIN_NAME = os.environ.get('INITIAL_ADMIN_NAME', 'Super Admin')
    INITIAL_ADMIN_USERNAME = os.environ.get('INITIAL_ADMIN_USERNAME', 'admin')
    INITIAL_ADMIN_EMAIL = os.environ.get('INITIAL_ADMIN_EMAIL', 'admin@example.com')
    INITIAL_ADMIN_PHONE = os.environ.get('INITIAL_ADMIN_PHONE', '+6281234567890')
    INITIAL_ADMIN_PASSWORD = os.environ.get('INITIAL_ADMIN_PASSWORD', 'AdminPassword123!')

    # VAPID Web Push
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
    VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:admin@example.com')

    # File Uploads Configuration
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'instance', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'csv', 'zip'}

