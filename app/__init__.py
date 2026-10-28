import os
import json
import base64
from flask import Flask, send_from_directory, redirect, url_for
from flask_login import current_user
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from dotenv import set_key

from config import Config
from app.extensions import db, migrate, login_manager, csrf


def _ensure_vapid_keys(app):
    """Auto-generate and persist ECDSA P-256 VAPID keys if not present."""
    pub = (app.config.get("VAPID_PUBLIC_KEY") or "").strip()
    priv = (app.config.get("VAPID_PRIVATE_KEY") or "").strip()
    if pub and priv:
        return

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get('UPLOAD_FOLDER', os.path.join(app.instance_path, 'uploads')), exist_ok=True)
    vapid_file = os.path.join(app.instance_path, "vapid_keys.json")

    if os.path.exists(vapid_file):
        try:
            with open(vapid_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                loaded_pub = data.get("public_key", "").strip()
                loaded_priv = data.get("private_key", "").strip()
                if loaded_pub and loaded_priv:
                    app.config["VAPID_PUBLIC_KEY"] = loaded_pub
                    app.config["VAPID_PRIVATE_KEY"] = loaded_priv
                    return
        except Exception:
            pass

    # Generate new ECDSA P-256 keypair in URL-safe Base64 (unpadded)
    private_key = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder="big")
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("utf-8")
    priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode("utf-8")

    try:
        with open(vapid_file, "w", encoding="utf-8") as f:
            json.dump({"public_key": pub_b64, "private_key": priv_b64}, f, indent=2)
    except Exception as e:
        app.logger.warning(f"Could not persist vapid_keys.json to disk: {e}")

    env_path = os.path.join(os.path.dirname(app.root_path), ".env")
    if os.path.exists(env_path) and os.access(env_path, os.W_OK):
        try:
            set_key(env_path, "VAPID_PUBLIC_KEY", pub_b64)
            set_key(env_path, "VAPID_PRIVATE_KEY", priv_b64)
        except Exception:
            pass

    app.config["VAPID_PUBLIC_KEY"] = pub_b64
    app.config["VAPID_PRIVATE_KEY"] = priv_b64


def _ensure_initial_admin(app):
    """Auto-provision the initial Admin user from .env if not existing.
    Also ensures database schema is initialized if migrations were not executed.
    """
    with app.app_context():
        # Step 1: Ensure tables exist
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if not inspector.has_table('users'):
                app.logger.info("Tabel basis data belum ditemukan. Menjalankan inisialisasi skema...")
                try:
                    from flask_migrate import upgrade
                    upgrade()
                    app.logger.info("Migrasi database berhasil dijalankan otomatis.")
                except Exception as mig_err:
                    app.logger.warning(f"flask_migrate upgrade gagal: {mig_err}. Menggunakan db.create_all().")
                    db.create_all()
        except Exception as schema_err:
            app.logger.warning(f"Pemeriksaan skema basis data gagal: {schema_err}")

        # Step 2: Auto-provision initial Admin
        try:
            from app.models import User, RoleEnum
            admin_username = app.config.get("INITIAL_ADMIN_USERNAME", "admin").strip().lower()
            admin_email = app.config.get("INITIAL_ADMIN_EMAIL", "admin@example.com").strip().lower()
            existing = User.query.filter(
                db.or_(
                    db.func.lower(User.username) == admin_username,
                    db.func.lower(User.email) == admin_email
                )
            ).first()
            if not existing:
                admin_name = app.config.get("INITIAL_ADMIN_NAME", "Super Admin")
                admin_phone = app.config.get("INITIAL_ADMIN_PHONE", "+6281234567890")
                admin_password = app.config.get("INITIAL_ADMIN_PASSWORD", "AdminPassword123!")
                admin = User(
                    username=admin_username,
                    name=admin_name,
                    email=admin_email,
                    phone_number=admin_phone,
                    role=RoleEnum.ADMIN,
                    is_active=True
                )
                admin.set_password(admin_password)
                db.session.add(admin)
                db.session.commit()
                app.logger.info(f"Pengguna Admin inisial '{admin_username}' berhasil dibuat.")
        except Exception as user_err:
            db.session.rollback()
            app.logger.error(f"Gagal memverifikasi/membuat pengguna Admin inisial: {user_err}")


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get('UPLOAD_FOLDER', os.path.join(app.instance_path, 'uploads')), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.admin.routes import admin_bp
    from app.blueprints.tasks.routes import tasks_bp
    from app.blueprints.notifications.routes import notifications_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(notifications_bp, url_prefix='/notifications')

    # Root route
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            try:
                return redirect(url_for('tasks.index'))
            except Exception:
                return "TaskOps Core Online (Authenticated)", 200
        try:
            return redirect(url_for('auth.login'))
        except Exception:
            return "TaskOps Core Online", 200

    # PWA Manifest & Service Worker Routes
    @app.route('/manifest.json')
    def manifest():
        manifest_path = os.path.join(app.root_path, 'templates', 'manifest.json')
        if not os.path.exists(manifest_path):
            return {"name": "TaskOps"}, 200, {'Content-Type': 'application/manifest+json'}
        response = send_from_directory(
            os.path.join(app.root_path, 'templates'),
            'manifest.json',
            mimetype='application/manifest+json'
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    @app.route('/sw.js')
    def service_worker():
        sw_path = os.path.join(app.root_path, 'templates', 'sw.js')
        if not os.path.exists(sw_path):
            response = app.response_class("// TaskOps SW Placeholder", mimetype='application/javascript')
            response.headers['Service-Worker-Allowed'] = '/'
            return response
        response = send_from_directory(
            os.path.join(app.root_path, 'templates'),
            'sw.js',
            mimetype='application/javascript'
        )
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    # Auto-generate VAPID keys and auto-provision initial admin
    _ensure_vapid_keys(app)
    _ensure_initial_admin(app)

    return app

