from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from app.extensions import db
from app.models import User, PushSubscription

auth_bp = Blueprint('auth', __name__)


def is_safe_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('tasks.index'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not identifier or not password:
            flash('Please enter both your identifier and password.', 'error')
            return render_template('auth/login.html')

        try:
            user = User.query.filter(
                db.or_(
                    db.func.lower(User.username) == identifier.lower(),
                    db.func.lower(User.email) == identifier.lower(),
                    User.phone_number == identifier
                )
            ).first()
        except Exception as e:
            current_app.logger.error(f"Database query error during login: {e}", exc_info=True)
            flash('Terjadi kesalahan pada basis data. Silakan hubungi administrator atau jalankan migrasi database.', 'error')
            return render_template('auth/login.html'), 500

        if not user or not user.check_password(password):
            flash('Invalid username, phone number, or password.', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Please contact an administrator.', 'error')
            return render_template('auth/login.html')

        login_user(user, remember=remember)

        next_page = request.args.get('next')
        if next_page and is_safe_url(next_page):
            return redirect(next_page)
        return redirect(url_for('tasks.index'))

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            current_pass = request.form.get('current_password', '')
            new_pass = request.form.get('new_password', '')
            confirm_pass = request.form.get('confirm_password', '')

            if not current_user.check_password(current_pass):
                flash('Kata sandi saat ini tidak cocok.', 'error')
                return redirect(url_for('auth.profile'))

            if not new_pass or len(new_pass) < 6:
                flash('Kata sandi baru minimal 6 karakter.', 'error')
                return redirect(url_for('auth.profile'))

            if new_pass != confirm_pass:
                flash('Konfirmasi kata sandi baru tidak cocok.', 'error')
                return redirect(url_for('auth.profile'))

            current_user.set_password(new_pass)
            try:
                db.session.commit()
                flash('Kata sandi Anda berhasil diperbarui.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Gagal memperbarui kata sandi: {e}', 'error')

            return redirect(url_for('auth.profile'))

    # Hitung metrik tugas untuk pengguna saat ini
    from app.models.task import Task
    from app.models.enums import TaskStatus

    team_ids = [t.id for t in current_user.active_teams]
    user_tasks_query = Task.query.filter(
        Task.is_archived == False,
        (
            (Task.assigned_user_id == current_user.id) |
            (Task.assigned_team_id.in_(team_ids) if team_ids else False)
        )
    )
    user_tasks = user_tasks_query.all()
    metrics = {
        'total': len(user_tasks),
        'completed': sum(1 for t in user_tasks if t.status == TaskStatus.COMPLETED),
        'in_progress': sum(1 for t in user_tasks if t.status == TaskStatus.IN_PROGRESS),
        'pending': sum(1 for t in user_tasks if t.status == TaskStatus.PENDING),
    }

    return render_template('auth/profile.html', user=current_user, metrics=metrics)


@auth_bp.route('/push-subscribe', methods=['POST'])
@login_required
def push_subscribe():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid JSON body'}), 400

    endpoint = data.get('endpoint')
    keys = data.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({'status': 'error', 'message': 'Missing push subscription fields'}), 400

    subscription = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not subscription:
        subscription = PushSubscription(
            user_id=current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth
        )
        db.session.add(subscription)
    else:
        subscription.user_id = current_user.id
        subscription.p256dh = p256dh
        subscription.auth = auth

    try:
        db.session.commit()
        current_app.logger.info(
            f"[WebPush] Saved subscription #{subscription.id} for user #{current_user.id} (@{current_user.username})"
        )
        return jsonify({'status': 'success', 'message': 'Push subscription saved'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[WebPush] Failed to save push subscription: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
