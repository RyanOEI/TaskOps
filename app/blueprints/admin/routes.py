from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    User, Team, Task, SubTask, ItemRequest, RoleEnum, TaskStatus, ItemStatus,
    validate_username, validate_e164_phone, has_user_history, has_team_history
)
from app.services.notification import notify_user, notify_team, notify_all_admins
from app.services.activity import log_activity

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    """Dekorator untuk memastikan hanya pengguna dengan peran ADMIN yang dapat mengakses."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('Akses ditolak: Anda memerlukan hak akses Administrator untuk membuka halaman ini.', 'error')
            return redirect(url_for('tasks.index'))
        return f(*args, **kwargs)
    return decorated_function


def is_ajax_request():
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.is_json or
        'application/json' in request.headers.get('Accept', '')
    )


def handle_form_error(message, redirect_endpoint='admin.users_list'):
    if is_ajax_request():
        return jsonify({'status': 'error', 'message': message}), 400
    flash(message, 'error')
    return redirect(url_for(redirect_endpoint))


def handle_form_success(message, redirect_endpoint='admin.users_list'):
    flash(message, 'success')
    if is_ajax_request():
        return jsonify({'status': 'success', 'message': message, 'redirect_url': url_for(redirect_endpoint)})
    return redirect(url_for(redirect_endpoint))


# ==============================================================================
# MANAJEMEN PENGGUNA (USERS)
# ==============================================================================

@admin_bp.route('/users', methods=['GET'])
@login_required
@admin_required
def users_list():
    tab = request.args.get('tab', 'active')
    if tab == 'inactive':
        users = User.query.filter_by(is_active=False).order_by(User.name.asc()).all()
    elif tab == 'all':
        users = User.query.order_by(User.name.asc()).all()
    else:
        tab = 'active'
        users = User.query.filter_by(is_active=True).order_by(User.name.asc()).all()

    counts = {
        'active': User.query.filter_by(is_active=True).count(),
        'inactive': User.query.filter_by(is_active=False).count(),
        'all': User.query.count()
    }
    return render_template('admin/users.html', users=users, current_tab=tab, counts=counts, RoleEnum=RoleEnum)


@admin_bp.route('/users', methods=['POST'])
@login_required
@admin_required
def user_create():
    username = request.form.get('username', '').strip().lower()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower() or None
    phone_number = request.form.get('phone_number', '').strip() or None
    password = request.form.get('password', '')
    role_str = request.form.get('role', RoleEnum.STAFF.value)

    # Validasi Username
    if not validate_username(username):
        return handle_form_error('Username tidak valid: Gunakan 3–30 karakter alfanumerik, titik, atau garis bawah.')

    if User.query.filter(db.func.lower(User.username) == username).first():
        return handle_form_error(f'Username "@{username}" sudah digunakan.')

    # Validasi Nama Lengkap
    if not name or len(name) < 2:
        return handle_form_error('Nama lengkap minimal 2 karakter.')

    # Validasi No Telepon E.164
    if phone_number:
        if not validate_e164_phone(phone_number):
            return handle_form_error('Nomor telepon harus berformat E.164 internasional (contoh: +6281234567890).')
        if User.query.filter_by(phone_number=phone_number).first():
            return handle_form_error(f'Nomor telepon {phone_number} sudah terdaftar pada akun lain.')

    # Validasi Email jika diisi
    if email:
        if User.query.filter(db.func.lower(User.email) == email).first():
            return handle_form_error(f'Email {email} sudah terdaftar pada akun lain.')

    # Validasi Kata Sandi
    if not password or len(password) < 6:
        return handle_form_error('Kata sandi minimal 6 karakter.')

    # Tentukan Peran
    try:
        role = RoleEnum(role_str)
    except ValueError:
        role = RoleEnum.STAFF

    new_user = User(
        username=username,
        name=name,
        email=email,
        phone_number=phone_number,
        role=role,
        is_active=True
    )
    new_user.set_password(password)

    db.session.add(new_user)
    try:
        db.session.commit()
        return handle_form_success(f'Pengguna "@{username}" ({name}) berhasil dibuat.')
    except Exception as e:
        db.session.rollback()
        return handle_form_error(f'Gagal menyimpan pengguna baru: {e}')


@admin_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def user_edit(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return handle_form_error('Pengguna tidak ditemukan.')

    username = request.form.get('username', '').strip().lower()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower() or None
    phone_number = request.form.get('phone_number', '').strip() or None
    role_str = request.form.get('role', user.role.value)

    if not validate_username(username):
        return handle_form_error('Username tidak valid: Gunakan 3–30 karakter alfanumerik, titik, atau garis bawah.')

    existing_username = User.query.filter(db.func.lower(User.username) == username, User.id != user.id).first()
    if existing_username:
        return handle_form_error(f'Username "@{username}" sudah digunakan oleh akun lain.')

    if not name or len(name) < 2:
        return handle_form_error('Nama lengkap minimal 2 karakter.')

    if phone_number:
        if not validate_e164_phone(phone_number):
            return handle_form_error('Nomor telepon harus berformat E.164 internasional (contoh: +6281234567890).')
        existing_phone = User.query.filter(User.phone_number == phone_number, User.id != user.id).first()
        if existing_phone:
            return handle_form_error(f'Nomor telepon {phone_number} sudah terdaftar pada akun lain.')

    if email:
        existing_email = User.query.filter(db.func.lower(User.email) == email, User.id != user.id).first()
        if existing_email:
            return handle_form_error(f'Email {email} sudah terdaftar pada akun lain.')

    # Perlindungan self-demotion admin
    try:
        new_role = RoleEnum(role_str)
    except ValueError:
        new_role = user.role

    if user.id == current_user.id and new_role != RoleEnum.ADMIN:
        return handle_form_error('Anda tidak dapat menurunkan hak akses peran Administrator untuk akun Anda sendiri.')

    user.username = username
    user.name = name
    user.email = email
    user.phone_number = phone_number
    user.role = new_role

    try:
        db.session.commit()
        return handle_form_success(f'Profil pengguna @{user.username} berhasil diperbarui.')
    except Exception as e:
        db.session.rollback()
        return handle_form_error(f'Gagal memperbarui pengguna: {e}')


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def user_reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return handle_form_error('Pengguna tidak ditemukan.')

    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not new_password or len(new_password) < 6:
        return handle_form_error('Kata sandi baru minimal 6 karakter.')

    if new_password != confirm_password:
        return handle_form_error('Konfirmasi kata sandi tidak cocok.')

    user.set_password(new_password)
    try:
        db.session.commit()
        return handle_form_success(f'Kata sandi untuk pengguna @{user.username} berhasil diubah.')
    except Exception as e:
        db.session.rollback()
        return handle_form_error(f'Gagal mengubah kata sandi: {e}')


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def user_delete(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('Pengguna tidak ditemukan.', 'error')
        return redirect(url_for('admin.users_list'))

    # Perlindungan admin menghapus diri sendiri
    if user.id == current_user.id:
        flash('Anda tidak dapat menghapus akun Administrator yang sedang Anda gunakan.', 'error')
        return redirect(url_for('admin.users_list'))

    # Penting: Lepaskan keanggotaan tim segera agar tidak lagi tercatat di tim mana pun
    user.teams = []

    # Smart Deletion: Cek apakah memiliki riwayat historis
    if has_user_history(user):
        user.is_active = False
        try:
            db.session.commit()
            flash(
                f'Pengguna @{user.username} memiliki riwayat tugas atau permintaan material terkait, '
                f'sehingga akun dinonaktifkan (diarsipkan) dan dilepas dari seluruh tim.',
                'info'
            )
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menonaktifkan akun: {e}', 'error')
    else:
        # Bersih tanpa riwayat: hapus baris DB permanen
        db.session.delete(user)
        try:
            db.session.commit()
            flash(f'Pengguna @{user.username} berhasil dihapus secara permanen dari sistem.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menghapus pengguna: {e}', 'error')

    return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/reactivate', methods=['POST'])
@login_required
@admin_required
def user_reactivate(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('Pengguna tidak ditemukan.', 'error')
        return redirect(url_for('admin.users_list'))

    user.is_active = True
    try:
        db.session.commit()
        flash(f'Akun pengguna @{user.username} berhasil diaktifkan kembali.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal mengaktifkan kembali akun: {e}', 'error')

    return redirect(url_for('admin.users_list'))


# ==============================================================================
# MANAJEMEN TIM (TEAMS)
# ==============================================================================

@admin_bp.route('/teams', methods=['GET'])
@login_required
@admin_required
def teams_list():
    tab = request.args.get('tab', 'active')
    if tab == 'inactive':
        teams = Team.query.filter_by(is_active=False).order_by(Team.name.asc()).all()
    elif tab == 'all':
        teams = Team.query.order_by(Team.name.asc()).all()
    else:
        tab = 'active'
        teams = Team.query.filter_by(is_active=True).order_by(Team.name.asc()).all()

    counts = {
        'active': Team.query.filter_by(is_active=True).count(),
        'inactive': Team.query.filter_by(is_active=False).count(),
        'all': Team.query.count()
    }

    # Hanya ambil pengguna aktif untuk pilihan penugasan anggota tim
    active_users = User.query.filter_by(is_active=True).order_by(User.name.asc()).all()

    return render_template(
        'admin/teams.html',
        teams=teams,
        active_users=active_users,
        current_tab=tab,
        counts=counts
    )


@admin_bp.route('/teams', methods=['POST'])
@login_required
@admin_required
def team_create():
    """Pembuatan Tim Baru: HANYA berisi Nama dan Deskripsi (tanpa pemilihan anggota)."""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None

    if not name or len(name) < 3:
        return handle_form_error('Nama tim minimal 3 karakter.', 'admin.teams_list')

    if Team.query.filter_by(name=name).first():
        return handle_form_error(f'Nama tim "{name}" sudah digunakan.', 'admin.teams_list')

    new_team = Team(
        name=name,
        description=description,
        is_active=True,
        members=[]
    )
    db.session.add(new_team)

    try:
        db.session.commit()
        return handle_form_success(f'Tim "{name}" berhasil dibuat. Silakan gunakan tombol "Kelola Anggota" untuk menetapkan anggota tim.', 'admin.teams_list')
    except Exception as e:
        db.session.rollback()
        return handle_form_error(f'Gagal membuat tim: {e}', 'admin.teams_list')


@admin_bp.route('/teams/<int:team_id>/edit', methods=['POST'])
@login_required
@admin_required
def team_edit(team_id):
    """Pengeditan Info Tim: HANYA memperbarui Nama dan Deskripsi."""
    team = db.session.get(Team, team_id)
    if not team:
        return handle_form_error('Tim tidak ditemukan.', 'admin.teams_list')

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None

    if not name or len(name) < 3:
        return handle_form_error('Nama tim minimal 3 karakter.', 'admin.teams_list')

    existing_name = Team.query.filter(Team.name == name, Team.id != team.id).first()
    if existing_name:
        return handle_form_error(f'Nama tim "{name}" sudah digunakan oleh tim lain.', 'admin.teams_list')

    team.name = name
    team.description = description

    try:
        db.session.commit()
        return handle_form_success(f'Info tim "{team.name}" berhasil diperbarui.', 'admin.teams_list')
    except Exception as e:
        db.session.rollback()
        return handle_form_error(f'Gagal memperbarui info tim: {e}', 'admin.teams_list')


@admin_bp.route('/teams/<int:team_id>/members-data', methods=['GET'])
@login_required
@admin_required
def team_members_data(team_id):
    """Mengembalikan data anggota aktif tim dan pengguna aktif yang tersedia dalam format JSON."""
    team = db.session.get(Team, team_id)
    if not team:
        return jsonify({'status': 'error', 'message': 'Tim tidak ditemukan'}), 404

    current_members = [
        {
            'id': m.id,
            'name': m.name,
            'username': m.username,
            'role': m.role.value
        }
        for m in team.active_members
    ]

    current_member_ids = {m['id'] for m in current_members}

    available_users = [
        {
            'id': u.id,
            'name': u.name,
            'username': u.username,
            'role': u.role.value
        }
        for u in User.query.filter_by(is_active=True).order_by(User.name.asc()).all()
        if u.id not in current_member_ids
    ]

    return jsonify({
        'status': 'success',
        'team_id': team.id,
        'team_name': team.name,
        'current_members': current_members,
        'available_users': available_users
    })


@admin_bp.route('/teams/<int:team_id>/members', methods=['POST'])
@login_required
@admin_required
def team_manage_members(team_id):
    """Menyimpan pembaruan daftar anggota tim via modal chip."""
    team = db.session.get(Team, team_id)
    if not team:
        return handle_form_error('Tim tidak ditemukan.', 'admin.teams_list')

    member_ids = request.form.getlist('member_ids')
    selected_users = []
    if member_ids:
        try:
            ids = [int(uid) for uid in member_ids]
            selected_users = User.query.filter(User.id.in_(ids), User.is_active == True).all()
        except ValueError:
            pass

    team.members = selected_users
    try:
        db.session.commit()
        return handle_form_success(f'Daftar anggota untuk Tim "{team.name}" berhasil diperbarui ({len(selected_users)} anggota).', 'admin.teams_list')
    except Exception as e:
        db.session.rollback()
        return handle_form_error(f'Gagal memperbarui anggota tim: {e}', 'admin.teams_list')


@admin_bp.route('/teams/<int:team_id>/delete', methods=['POST'])
@login_required
@admin_required
def team_delete(team_id):
    team = db.session.get(Team, team_id)
    if not team:
        flash('Tim tidak ditemukan.', 'error')
        return redirect(url_for('admin.teams_list'))

    # Smart Deletion: Cek apakah memiliki riwayat tugas
    if has_team_history(team):
        team.is_active = False
        team.members = []  # Segera putus keanggotaan semua pengguna dari tim nonaktif
        try:
            db.session.commit()
            flash(
                f'Tim "{team.name}" memiliki riwayat tugas terkait, sehingga dinonaktifkan (diarsipkan) '
                f'dan tidak dihapus permanen demi integritas data.',
                'info'
            )
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menonaktifkan tim: {e}', 'error')
    else:
        # Bersih tanpa riwayat: lepas keanggotaan lalu hapus permanen
        team.members = []
        db.session.delete(team)
        try:
            db.session.commit()
            flash(f'Tim "{team.name}" berhasil dihapus secara permanen.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menghapus tim: {e}', 'error')

    return redirect(url_for('admin.teams_list'))


@admin_bp.route('/teams/<int:team_id>/reactivate', methods=['POST'])
@login_required
@admin_required
def team_reactivate(team_id):
    team = db.session.get(Team, team_id)
    if not team:
        flash('Tim tidak ditemukan.', 'error')
        return redirect(url_for('admin.teams_list'))

    team.is_active = True
    try:
        db.session.commit()
        flash(f'Tim "{team.name}" berhasil diaktifkan kembali.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal mengaktifkan kembali tim: {e}', 'error')

    return redirect(url_for('admin.teams_list'))


# =========================================================================
# LOGISTIK MATERIAL GLOBAL (LANGKAH 42)
# =========================================================================
@admin_bp.route('/logistics', methods=['GET'])
@login_required
@admin_required
def logistics():
    tab = request.args.get('tab', 'all')
    all_items = ItemRequest.query.order_by(ItemRequest.requested_at.desc()).all()

    counts = {
        'all': len(all_items),
        'REQUESTED': sum(1 for it in all_items if it.status == ItemStatus.REQUESTED),
        'ORDERED': sum(1 for it in all_items if it.status == ItemStatus.ORDERED),
        'SHIPPED': sum(1 for it in all_items if it.status == ItemStatus.SHIPPED),
        'RECEIVED': sum(1 for it in all_items if it.status == ItemStatus.RECEIVED),
    }

    if tab != 'all' and tab in ItemStatus.__members__:
        filtered_items = [it for it in all_items if it.status.value == tab]
    else:
        tab = 'all'
        filtered_items = all_items

    # Kelompokkan item berdasarkan Task untuk tampilan rapi
    grouped_tasks = {}
    for it in filtered_items:
        t = it.task
        if t.id not in grouped_tasks:
            grouped_tasks[t.id] = {
                'task': t,
                'item_list': [],
                'has_requested': False,
                'has_ordered': False
            }
        grouped_tasks[t.id]['item_list'].append(it)
        if it.status == ItemStatus.REQUESTED:
            grouped_tasks[t.id]['has_requested'] = True
        elif it.status == ItemStatus.ORDERED:
            grouped_tasks[t.id]['has_ordered'] = True

    return render_template(
        'admin/logistics.html',
        grouped_tasks=list(grouped_tasks.values()),
        counts=counts,
        current_tab=tab,
        ItemStatus=ItemStatus
    )


@admin_bp.route('/logistics/<int:item_id>/order', methods=['POST'])
@login_required
@admin_required
def item_order(item_id):
    item = db.session.get(ItemRequest, item_id)
    if not item:
        flash('Item material tidak ditemukan.', 'error')
        return redirect(url_for('admin.logistics'))

    if item.status != ItemStatus.REQUESTED:
        flash('Hanya item dengan status Diajukan yang dapat ditandai Dipesan.', 'error')
        return redirect(url_for('admin.logistics'))

    item.status = ItemStatus.ORDERED
    item.ordered_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
        log_activity(item.task_id, current_user.id, "MATERIAL_ORDERED", f"Material '{item.item_name}' ({item.quantity}) ditandai Dipesan.")
        notify_user(
            item.requested_by_id,
            title=f"Material Dipesan: {item.item_name}",
            message=f"Material '{item.item_name}' ({item.quantity}) untuk tugas '{item.task.title}' telah dipesan oleh Administrator.",
            target_url=f"/tasks/{item.task_id}"
        )
        flash(f'Material "{item.item_name}" berhasil ditandai Dipesan.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memperbarui status material: {e}', 'error')

    return redirect(url_for('admin.logistics'))


@admin_bp.route('/logistics/<int:item_id>/ship', methods=['POST'])
@login_required
@admin_required
def item_ship(item_id):
    item = db.session.get(ItemRequest, item_id)
    if not item:
        flash('Item material tidak ditemukan.', 'error')
        return redirect(url_for('admin.logistics'))

    if item.status != ItemStatus.ORDERED:
        flash('Hanya item dengan status Dipesan yang dapat ditandai Dikirim.', 'error')
        return redirect(url_for('admin.logistics'))

    item.status = ItemStatus.SHIPPED
    item.shipped_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
        log_activity(item.task_id, current_user.id, "MATERIAL_SHIPPED", f"Material '{item.item_name}' ({item.quantity}) ditandai Dikirim.")
        notify_user(
            item.requested_by_id,
            title=f"Material Dikirim: {item.item_name}",
            message=f"Material '{item.item_name}' ({item.quantity}) untuk tugas '{item.task.title}' sedang dikirim ke lokasi lapangan.",
            target_url=f"/tasks/{item.task_id}"
        )
        flash(f'Material "{item.item_name}" berhasil ditandai Dikirim.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memperbarui status material: {e}', 'error')

    return redirect(url_for('admin.logistics'))


@admin_bp.route('/logistics/<int:item_id>/reject', methods=['POST'])
@login_required
@admin_required
def item_reject(item_id):
    item = db.session.get(ItemRequest, item_id)
    if not item:
        flash('Item material tidak ditemukan.', 'error')
        return redirect(url_for('admin.logistics'))

    if item.status != ItemStatus.REQUESTED:
        flash('Hanya item dengan status Diajukan yang dapat ditolak.', 'error')
        return redirect(url_for('admin.logistics'))

    reason = request.form.get('rejection_reason', '').strip()
    if not reason:
        flash('Alasan penolakan material wajib diisi.', 'error')
        return redirect(url_for('admin.logistics'))

    item.status = ItemStatus.REJECTED
    item.rejection_reason = reason

    try:
        db.session.commit()
        log_activity(item.task_id, current_user.id, "MATERIAL_REJECTED", f"Material '{item.item_name}' ditolak: {reason}")
        notify_user(
            item.requested_by_id,
            title=f"Material Ditolak: {item.item_name}",
            message=f"Pengajuan material '{item.item_name}' untuk tugas '{item.task.title}' ditolak oleh Administrator. Alasan: {reason}",
            target_url=f"/tasks/{item.task_id}"
        )
        flash(f'Material "{item.item_name}" berhasil ditolak dengan alasan.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menolak material: {e}', 'error')

    return redirect(url_for('admin.logistics'))


@admin_bp.route('/logistics/tasks/<int:task_id>/order-all', methods=['POST'])
@login_required
@admin_required
def task_order_all_items(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('admin.logistics'))

    requested_items = [it for it in task.item_requests if it.status == ItemStatus.REQUESTED]
    if not requested_items:
        flash('Tidak ada item yang berstatus Diajukan pada tugas ini.', 'info')
        return redirect(url_for('admin.logistics'))

    now = datetime.now(timezone.utc)
    for it in requested_items:
        it.status = ItemStatus.ORDERED
        it.ordered_at = now

    try:
        db.session.commit()
        requester_ids = {it.requested_by_id for it in requested_items}
        for uid in requester_ids:
            notify_user(
                uid,
                title=f"Material Dipesan ({len(requested_items)} item)",
                message=f"Seluruh pengajuan material untuk tugas '{task.title}' telah dipesan oleh Administrator.",
                target_url=f"/tasks/{task.id}"
            )
        flash(f'Berhasil menandai {len(requested_items)} material sebagai Dipesan untuk tugas "{task.title}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memproses pesanan batch: {e}', 'error')

    return redirect(url_for('admin.logistics'))


@admin_bp.route('/logistics/tasks/<int:task_id>/ship-all', methods=['POST'])
@login_required
@admin_required
def task_ship_all_items(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('admin.logistics'))

    ordered_items = [it for it in task.item_requests if it.status == ItemStatus.ORDERED]
    if not ordered_items:
        flash('Tidak ada item yang berstatus Dipesan pada tugas ini.', 'info')
        return redirect(url_for('admin.logistics'))

    now = datetime.now(timezone.utc)
    for it in ordered_items:
        it.status = ItemStatus.SHIPPED
        it.shipped_at = now

    try:
        db.session.commit()
        requester_ids = {it.requested_by_id for it in ordered_items}
        for uid in requester_ids:
            notify_user(
                uid,
                title=f"Material Dikirim ({len(ordered_items)} item)",
                message=f"Seluruh material pesanan untuk tugas '{task.title}' sedang dikirim ke lokasi.",
                target_url=f"/tasks/{task.id}"
            )
        flash(f'Berhasil menandai {len(ordered_items)} material sebagai Dikirim untuk tugas "{task.title}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memproses pengiriman batch: {e}', 'error')

    return redirect(url_for('admin.logistics'))


# =========================================================================
# ANTREAN EVALUASI REVIEW TUGAS (LANGKAH 46)
# =========================================================================
@admin_bp.route('/review-queue', methods=['GET'])
@login_required
@admin_required
def review_queue():
    tasks = Task.query.filter_by(status=TaskStatus.WAITING_REVIEW).order_by(Task.created_at.desc()).all()
    return render_template(
        'admin/review_queue.html',
        tasks=tasks,
        TaskStatus=TaskStatus,
        ItemStatus=ItemStatus
    )


@admin_bp.route('/review-queue/<int:task_id>/approve', methods=['POST'])
@login_required
@admin_required
def review_approve(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('admin.review_queue'))

    if task.status != TaskStatus.WAITING_REVIEW:
        flash('Tugas tidak sedang dalam status Menunggu Review.', 'error')
        return redirect(url_for('admin.review_queue'))

    task.status = TaskStatus.COMPLETED

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "TASK_COMPLETED", "Tugas disetujui oleh Administrator dan berstatus Selesai (COMPLETED).")
        msg = f"Selamat! Hasil pekerjaan tugas '{task.title}' telah disetujui oleh Administrator dan dinyatakan selesai sepenuhnya."
        if task.assigned_user_id:
            notify_user(task.assigned_user_id, title="Tugas Disetujui (Selesai)", message=msg, target_url=f"/tasks/{task.id}")
        elif task.assigned_team_id:
            notify_team(task.assigned_team_id, title="Tugas Tim Disetujui (Selesai)", message=msg, target_url=f"/tasks/{task.id}")

        flash(f'Tugas "{task.title}" berhasil disetujui dan berstatus Selesai (COMPLETED).', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menyetujui tugas: {e}', 'error')

    return redirect(url_for('admin.review_queue'))


@admin_bp.route('/review-queue/<int:task_id>/request-continuation', methods=['POST'])
@login_required
@admin_required
def review_request_continuation(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('admin.review_queue'))

    if task.status != TaskStatus.WAITING_REVIEW:
        flash('Tugas tidak sedang dalam status Menunggu Review.', 'error')
        return redirect(url_for('admin.review_queue'))

    notes = request.form.get('review_notes', '').strip()
    if not notes or len(notes) < 3:
        flash('Catatan evaluasi / perbaikan wajib diisi minimal 3 karakter.', 'error')
        return redirect(url_for('admin.review_queue'))

    task.status = TaskStatus.IN_PROGRESS
    task.review_notes = notes

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "REVIEW_REVISION_REQUESTED", f"Catatan perbaikan Administrator: {notes}")
        msg = f"Tugas '{task.title}' memerlukan perbaikan / tindak lanjut. Catatan dari Administrator: {notes}"
        if task.assigned_user_id:
            notify_user(task.assigned_user_id, title="Perbaikan Tugas Diperlukan", message=msg, target_url=f"/tasks/{task.id}")
        elif task.assigned_team_id:
            notify_team(task.assigned_team_id, title="Perbaikan Tugas Tim Diperlukan", message=msg, target_url=f"/tasks/{task.id}")

        flash(f'Tugas "{task.title}" dikembalikan ke status Sedang Dikerjakan dengan catatan perbaikan.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal meminta perbaikan tugas: {e}', 'error')

    return redirect(url_for('admin.review_queue'))
