import os
import uuid
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import (
    Task, SubTask, ItemRequest, Attachment, User, Team, TaskStatus, TaskPriority, ItemStatus,
    is_authorized_for_task
)
from app.blueprints.admin.routes import admin_required
from app.services.notification import notify_user, notify_team, notify_all_admins
from app.services.activity import log_activity

tasks_bp = Blueprint('tasks', __name__)


def is_ajax():
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('HX-Request') == 'true' or
        request.is_json or
        'application/json' in request.headers.get('Accept', '')
    )


# =========================================================================
# 1. DASBOR TUGAS (FILTER TABS, PRIORITY FILTER, KPI, & PENCARIAN)
# =========================================================================
@tasks_bp.route('/', methods=['GET'])
@login_required
def index():
    tab = request.args.get('tab', 'all')
    priority_filter = request.args.get('priority', 'all')

    # Scoping tugas berdasarkan hak akses (hanya tugas yang belum diarsipkan)
    if current_user.is_admin:
        base_query = Task.query.filter_by(is_archived=False)
    else:
        team_ids = [t.id for t in current_user.active_teams]
        base_query = Task.query.filter(
            Task.is_archived == False,
            (
                (Task.assigned_user_id == current_user.id) |
                (Task.assigned_team_id.in_(team_ids) if team_ids else False) |
                (Task.created_by_id == current_user.id)
            )
        )

    all_scoped = base_query.order_by(Task.created_at.desc()).all()

    today = date.today()

    # Hitung KPI untuk statistik dasbor
    kpi = {
        'total_active': sum(1 for t in all_scoped if t.status != TaskStatus.COMPLETED),
        'overdue': sum(1 for t in all_scoped if t.due_date and t.status != TaskStatus.COMPLETED and t.due_date < today),
        'waiting_review': sum(1 for t in all_scoped if t.status == TaskStatus.WAITING_REVIEW),
        'pending': sum(1 for t in all_scoped if t.status == TaskStatus.PENDING),
    }

    # Hitung jumlah untuk setiap tab status
    counts = {
        'all': len(all_scoped),
        'TODO': sum(1 for t in all_scoped if t.status == TaskStatus.TODO),
        'IN_PROGRESS': sum(1 for t in all_scoped if t.status == TaskStatus.IN_PROGRESS),
        'PENDING': sum(1 for t in all_scoped if t.status == TaskStatus.PENDING),
        'WAITING_REVIEW': sum(1 for t in all_scoped if t.status == TaskStatus.WAITING_REVIEW),
        'COMPLETED': sum(1 for t in all_scoped if t.status == TaskStatus.COMPLETED),
    }

    # Filter berdasarkan tab status
    if tab != 'all' and tab in TaskStatus.__members__:
        filtered = [t for t in all_scoped if t.status.value == tab]
    else:
        tab = 'all'
        filtered = all_scoped

    # Filter berdasarkan prioritas jika dipilih
    if priority_filter != 'all' and priority_filter in TaskPriority.__members__:
        tasks = [t for t in filtered if t.priority.value == priority_filter]
    else:
        priority_filter = 'all'
        tasks = filtered

    return render_template(
        'tasks/index.html',
        tasks=tasks,
        counts=counts,
        kpi=kpi,
        current_tab=tab,
        current_priority=priority_filter,
        TaskStatus=TaskStatus,
        TaskPriority=TaskPriority
    )


# =========================================================================
# 2. PEMBUATAN TUGAS BARU (KHUSUS ADMIN)
# =========================================================================
@tasks_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    if request.method == 'GET':
        active_users = User.query.filter_by(is_active=True).order_by(User.name.asc()).all()
        active_teams = Team.query.filter_by(is_active=True).order_by(Team.name.asc()).all()
        return render_template(
            'tasks/create.html',
            users=active_users,
            teams=active_teams,
            TaskPriority=TaskPriority
        )

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    due_date_str = request.form.get('due_date', '').strip()
    priority_str = request.form.get('priority', TaskPriority.MEDIUM.value)
    assign_type = request.form.get('assign_type', 'team')
    assigned_user_id = None
    assigned_team_id = None

    if not title:
        flash('Judul tugas wajib diisi.', 'error')
        return redirect(url_for('tasks.create'))

    try:
        priority = TaskPriority(priority_str)
    except ValueError:
        priority = TaskPriority.MEDIUM

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Format tanggal tenggat tidak valid.', 'error')
            return redirect(url_for('tasks.create'))

    if assign_type == 'team':
        team_id_val = request.form.get('assigned_team_id')
        if not team_id_val:
            flash('Pilihlah tim operasional aktif untuk penugasan tugas ini.', 'error')
            return redirect(url_for('tasks.create'))
        assigned_team = db.session.get(Team, int(team_id_val))
        if not assigned_team or not assigned_team.is_active:
            flash('Tim yang dipilih tidak valid atau sudah nonaktif.', 'error')
            return redirect(url_for('tasks.create'))
        assigned_team_id = assigned_team.id
    elif assign_type == 'user':
        user_id_val = request.form.get('assigned_user_id')
        if not user_id_val:
            flash('Pilihlah pengguna aktif untuk penugasan tugas ini.', 'error')
            return redirect(url_for('tasks.create'))
        assigned_user = db.session.get(User, int(user_id_val))
        if not assigned_user or not assigned_user.is_active:
            flash('Pengguna yang dipilih tidak valid atau sudah nonaktif.', 'error')
            return redirect(url_for('tasks.create'))
        assigned_user_id = assigned_user.id
    else:
        flash('Pilihan penugasan tidak valid.', 'error')
        return redirect(url_for('tasks.create'))

    task = Task(
        title=title,
        description=description if description else None,
        priority=priority,
        due_date=due_date,
        status=TaskStatus.TODO,
        is_archived=False,
        created_by_id=current_user.id,
        assigned_user_id=assigned_user_id,
        assigned_team_id=assigned_team_id
    )

    try:
        db.session.add(task)
        db.session.commit()

        # Audit activity
        log_activity(
            task.id,
            current_user.id,
            "TASK_CREATED",
            f"Tugas dibuat dengan prioritas {priority.value}."
        )

        # Kirim notifikasi in-app & Web Push
        target_url = f"/tasks/{task.id}"
        prefix = "[URGENT] " if priority == TaskPriority.URGENT else ""
        if task.assigned_team_id:
            notify_team(
                task.assigned_team_id,
                title=f"{prefix}Tugas Baru untuk Tim",
                message=f"Tim Anda telah ditugaskan pada tugas: '{task.title}'",
                target_url=target_url
            )
        elif task.assigned_user_id:
            notify_user(
                task.assigned_user_id,
                title=f"{prefix}Tugas Baru Ditugaskan",
                message=f"Anda telah ditugaskan pada tugas: '{task.title}'",
                target_url=target_url
            )

        flash(f'Tugas "{task.title}" berhasil dibuat dan ditugaskan.', 'success')
        return redirect(url_for('tasks.detail', task_id=task.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal membuat tugas: {e}', 'error')
        return redirect(url_for('tasks.create'))


# =========================================================================
# 3. EDIT TUGAS (KHUSUS ADMIN)
# =========================================================================
@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if request.method == 'GET':
        active_users = User.query.filter_by(is_active=True).order_by(User.name.asc()).all()
        active_teams = Team.query.filter_by(is_active=True).order_by(Team.name.asc()).all()
        return render_template(
            'tasks/edit.html',
            task=task,
            users=active_users,
            teams=active_teams,
            TaskPriority=TaskPriority
        )

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    due_date_str = request.form.get('due_date', '').strip()
    priority_str = request.form.get('priority', task.priority.value)
    assign_type = request.form.get('assign_type', 'team')

    if not title:
        flash('Judul tugas wajib diisi.', 'error')
        return redirect(url_for('tasks.edit', task_id=task.id))

    try:
        task.priority = TaskPriority(priority_str)
    except ValueError:
        pass

    task.title = title
    task.description = description if description else None

    if due_date_str:
        try:
            task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Format tanggal tenggat tidak valid.', 'error')
            return redirect(url_for('tasks.edit', task_id=task.id))
    else:
        task.due_date = None

    if assign_type == 'team':
        team_id_val = request.form.get('assigned_team_id')
        if team_id_val:
            task.assigned_team_id = int(team_id_val)
            task.assigned_user_id = None
    elif assign_type == 'user':
        user_id_val = request.form.get('assigned_user_id')
        if user_id_val:
            task.assigned_user_id = int(user_id_val)
            task.assigned_team_id = None

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "TASK_EDITED", "Informasi tugas diperbarui oleh Administrator.")
        flash('Informasi tugas berhasil diperbarui.', 'success')
        return redirect(url_for('tasks.detail', task_id=task.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memperbarui tugas: {e}', 'error')
        return redirect(url_for('tasks.edit', task_id=task.id))


# =========================================================================
# 4. SOFT-ARCHIVE TUGAS (KHUSUS ADMIN)
# =========================================================================
@tasks_bp.route('/<int:task_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    task.is_archived = True
    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "TASK_ARCHIVED", "Tugas diarsipkan oleh Administrator.")
        flash(f'Tugas "{task.title}" berhasil diarsipkan.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal mengarsipkan tugas: {e}', 'error')

    return redirect(url_for('tasks.index'))


# =========================================================================
# 5. DETAIL TUGAS
# =========================================================================
@tasks_bp.route('/<int:task_id>', methods=['GET'])
@login_required
def detail(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak: Anda tidak memiliki izin untuk melihat tugas ini.', 'error')
        return redirect(url_for('tasks.index'))

    return render_template(
        'tasks/detail.html',
        task=task,
        subtasks=task.subtasks,
        item_requests=task.item_requests,
        activities=task.activities,
        TaskStatus=TaskStatus,
        TaskPriority=TaskPriority,
        ItemStatus=ItemStatus
    )


# =========================================================================
# 6. CETAK SURAT PERINTAH KERJA (PRINT WORK ORDER)
# =========================================================================
@tasks_bp.route('/<int:task_id>/print', methods=['GET'])
@login_required
def print_work_order(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.index'))

    return render_template(
        'tasks/print.html',
        task=task,
        subtasks=task.subtasks,
        item_requests=task.item_requests,
        TaskStatus=TaskStatus,
        TaskPriority=TaskPriority,
        ItemStatus=ItemStatus
    )


# =========================================================================
# 7. SUBTASK: TAMBAH SUBTASK (SHARED TEAM CHECKLIST)
# =========================================================================
@tasks_bp.route('/<int:task_id>/subtasks', methods=['POST'])
@login_required
def add_subtask(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Tugas tidak ditemukan.'}), 404
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    title = request.form.get('title', '').strip()
    if not title:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Nama subtask wajib diisi.'}), 400
        flash('Nama subtask tidak boleh kosong.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    subtask = SubTask(
        task_id=task.id,
        title=title,
        is_completed=False,
        created_by_id=current_user.id
    )
    db.session.add(subtask)

    # Transisi otomatis status tugas dari TODO / PENDING ke IN_PROGRESS
    if task.status in (TaskStatus.TODO, TaskStatus.PENDING):
        task.status = TaskStatus.IN_PROGRESS
        task.pending_reason = None

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "SUBTASK_ADDED", f"Subtask '{title}' ditambahkan.")
        if request.headers.get('HX-Request'):
            return render_template(
                'tasks/_subtasks_section.html',
                task=task,
                subtasks=task.subtasks,
                is_authorized=is_authorized_for_task(current_user, task)
            )
        if is_ajax():
            return jsonify({
                'status': 'success',
                'subtask': {
                    'id': subtask.id,
                    'title': subtask.title,
                    'is_completed': subtask.is_completed
                },
                'task_status': task.status.value
            })
        flash(f'Subtask "{title}" berhasil ditambahkan.', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax():
            return jsonify({'status': 'error', 'message': str(e)}), 500
        flash(f'Gagal menambahkan subtask: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 8. SUBTASK: CENTANG / BATAL SELESAI
# =========================================================================
@tasks_bp.route('/<int:task_id>/subtasks/<int:subtask_id>/toggle', methods=['POST'])
@login_required
def toggle_subtask(task_id, subtask_id):
    task = db.session.get(Task, task_id)
    if not task:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Tugas tidak ditemukan.'}), 404
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    subtask = db.session.get(SubTask, subtask_id)
    if not subtask or subtask.task_id != task.id:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Subtask tidak valid.'}), 404
        flash('Subtask tidak valid.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    # Simpan ringkasan jika disertakan dalam form saat mencentang
    summary = request.form.get('summary')
    if summary is not None and not subtask.is_completed:
        subtask.summary = summary.strip() or None

    subtask.is_completed = not subtask.is_completed

    # Transisi otomatis jika berstatus TODO / PENDING
    if task.status in (TaskStatus.TODO, TaskStatus.PENDING):
        task.status = TaskStatus.IN_PROGRESS
        task.pending_reason = None

    try:
        db.session.commit()
        status_txt = "selesai" if subtask.is_completed else "belum selesai"
        log_activity(task.id, current_user.id, "SUBTASK_TOGGLED", f"Subtask '{subtask.title}' ditandai {status_txt}.")
        if request.headers.get('HX-Request'):
            return render_template(
                'tasks/_subtasks_section.html',
                task=task,
                subtasks=task.subtasks,
                is_authorized=is_authorized_for_task(current_user, task)
            )
        if is_ajax():
            return jsonify({
                'status': 'success',
                'subtask_id': subtask.id,
                'is_completed': subtask.is_completed,
                'task_status': task.status.value
            })
    except Exception as e:
        db.session.rollback()
        if is_ajax():
            return jsonify({'status': 'error', 'message': str(e)}), 500
        flash(f'Gagal memperbarui subtask: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 8b. SUBTASK: SIMPAN RINGKASAN / DETAIL
# =========================================================================
@tasks_bp.route('/<int:task_id>/subtasks/<int:subtask_id>/summary', methods=['POST'])
@login_required
def update_subtask_summary(task_id, subtask_id):
    task = db.session.get(Task, task_id)
    if not task:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Tugas tidak ditemukan.'}), 404
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    subtask = db.session.get(SubTask, subtask_id)
    if not subtask or subtask.task_id != task.id:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Subtask tidak valid.'}), 404
        flash('Subtask tidak valid.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    if subtask.is_completed:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Subtask sudah selesai, batalkan centang untuk mengedit ringkasan.'}), 400
        flash('Subtask sudah selesai, batalkan centang untuk mengedit ringkasan.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    summary = request.form.get('summary', '').strip()
    subtask.summary = summary or None

    try:
        db.session.commit()
        if request.headers.get('HX-Request'):
            return render_template(
                'tasks/_subtasks_section.html',
                task=task,
                subtasks=task.subtasks,
                is_authorized=is_authorized_for_task(current_user, task)
            )
        if is_ajax():
            return jsonify({
                'status': 'success',
                'subtask_id': subtask.id,
                'summary': subtask.summary
            })
    except Exception as e:
        db.session.rollback()
        if is_ajax():
            return jsonify({'status': 'error', 'message': str(e)}), 500
        flash(f'Gagal menyimpan ringkasan subtask: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


def allowed_file(filename):
    allowed = current_app.config.get(
        'ALLOWED_EXTENSIONS',
        {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'csv', 'zip'}
    )
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


# =========================================================================
# 8c. LAMPIRAN: UNGGAH BERKAS TUGAS & SUBTASK
# =========================================================================
@tasks_bp.route('/<int:task_id>/attachments', methods=['POST'])
@login_required
def upload_task_attachment(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Tugas tidak ditemukan.'}), 404
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    # Optional subtask_id
    raw_subtask_id = request.form.get('subtask_id')
    subtask_id = None
    if raw_subtask_id:
        try:
            subtask_id = int(raw_subtask_id)
            subtask = db.session.get(SubTask, subtask_id)
            if not subtask or subtask.task_id != task.id:
                subtask_id = None
            elif subtask.is_completed:
                if is_ajax():
                    return jsonify({'status': 'error', 'message': 'Subtask sudah selesai, batalkan centang untuk menambah berkas.'}), 400
                flash('Subtask sudah selesai, batalkan centang untuk menambah berkas.', 'error')
                return redirect(url_for('tasks.detail', task_id=task.id))
        except (ValueError, TypeError):
            subtask_id = None

    uploaded_files = request.files.getlist('files')
    if not uploaded_files or (len(uploaded_files) == 1 and not uploaded_files[0].filename):
        single_file = request.files.get('file')
        if single_file and single_file.filename:
            uploaded_files = [single_file]
        else:
            if is_ajax():
                return jsonify({'status': 'error', 'message': 'Pilih berkas yang akan diunggah.'}), 400
            flash('Pilih berkas yang akan diunggah.', 'error')
            return redirect(url_for('tasks.detail', task_id=task.id))

    upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.instance_path, 'uploads'))
    os.makedirs(upload_folder, exist_ok=True)

    saved_count = 0
    for file in uploaded_files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            continue

        orig_name = secure_filename(file.filename) or "berkas"
        unique_prefix = uuid.uuid4().hex[:12]
        stored_filename = f"{unique_prefix}_{orig_name}"
        save_path = os.path.join(upload_folder, stored_filename)

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        file.save(save_path)
        mime_type = file.mimetype or 'application/octet-stream'

        attachment = Attachment(
            task_id=task.id,
            subtask_id=subtask_id,
            uploaded_by_id=current_user.id,
            filename=stored_filename,
            original_name=file.filename,
            file_size=file_size,
            mime_type=mime_type
        )
        db.session.add(attachment)
        saved_count += 1
        log_activity(task.id, current_user.id, "ATTACHMENT_UPLOADED", f"Berkas '{file.filename}' diunggah.")

    if saved_count > 0:
        db.session.commit()
        flash(f"{saved_count} berkas berhasil diunggah.", "success")
    else:
        flash("Format berkas tidak didukung atau berkas kosong.", "error")

    if request.headers.get('HX-Request'):
        if subtask_id:
            return render_template(
                'tasks/_subtasks_section.html',
                task=task,
                subtasks=task.subtasks,
                is_authorized=is_authorized_for_task(current_user, task),
                oob_attachments=True
            )
        return render_template(
            'tasks/_attachments_section.html',
            task=task,
            is_authorized=is_authorized_for_task(current_user, task)
        )

    return redirect(url_for('tasks.detail', task_id=task.id))


@tasks_bp.route('/<int:task_id>/subtasks/<int:subtask_id>/attachments', methods=['POST'])
@login_required
def upload_subtask_attachment(task_id, subtask_id):
    form_data = request.form.copy()
    form_data['subtask_id'] = str(subtask_id)
    request.form = form_data
    return upload_task_attachment(task_id)


# =========================================================================
# 8d. LAMPIRAN: LIHAT / PRATINJAU BERKAS
# =========================================================================
@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/view', methods=['GET'])
@login_required
def view_attachment(task_id, attachment_id):
    task = db.session.get(Task, task_id)
    if not task or not is_authorized_for_task(current_user, task):
        return "Akses ditolak", 403

    attachment = db.session.get(Attachment, attachment_id)
    if not attachment or attachment.task_id != task.id:
        return "Berkas tidak ditemukan", 404

    upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.instance_path, 'uploads'))
    return send_from_directory(
        upload_folder,
        attachment.filename,
        as_attachment=False,
        mimetype=attachment.mime_type
    )


# =========================================================================
# 8e. LAMPIRAN: UNDUH BERKAS
# =========================================================================
@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/download', methods=['GET'])
@login_required
def download_attachment(task_id, attachment_id):
    task = db.session.get(Task, task_id)
    if not task or not is_authorized_for_task(current_user, task):
        return "Akses ditolak", 403

    attachment = db.session.get(Attachment, attachment_id)
    if not attachment or attachment.task_id != task.id:
        return "Berkas tidak ditemukan", 404

    upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.instance_path, 'uploads'))
    return send_from_directory(
        upload_folder,
        attachment.filename,
        as_attachment=True,
        download_name=attachment.original_name
    )


# =========================================================================
# 8f. LAMPIRAN: HAPUS BERKAS
# =========================================================================
@tasks_bp.route('/<int:task_id>/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def delete_attachment(task_id, attachment_id):
    task = db.session.get(Task, task_id)
    if not task:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Tugas tidak ditemukan.'}), 404
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Akses ditolak.'}), 403
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    attachment = db.session.get(Attachment, attachment_id)
    if not attachment or attachment.task_id != task.id:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Berkas tidak ditemukan.'}), 404
        flash('Berkas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    if attachment.subtask and attachment.subtask.is_completed:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'Subtask sudah selesai, batalkan centang untuk menghapus berkas.'}), 400
        flash('Subtask sudah selesai, batalkan centang untuk menghapus berkas.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.instance_path, 'uploads'))
    file_path = os.path.join(upload_folder, attachment.filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    orig_name = attachment.original_name
    has_subtask = attachment.subtask_id is not None
    db.session.delete(attachment)

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "ATTACHMENT_DELETED", f"Berkas '{orig_name}' dihapus.")
        flash(f"Berkas '{orig_name}' berhasil dihapus.", "info")
    except Exception as e:
        db.session.rollback()
        if is_ajax():
            return jsonify({'status': 'error', 'message': str(e)}), 500
        flash(f"Gagal menghapus berkas: {e}", "error")

    if request.headers.get('HX-Request'):
        if has_subtask and request.args.get('from_subtask'):
            return render_template(
                'tasks/_subtasks_section.html',
                task=task,
                subtasks=task.subtasks,
                is_authorized=is_authorized_for_task(current_user, task),
                oob_attachments=True
            )
        return render_template(
            'tasks/_attachments_section.html',
            task=task,
            is_authorized=is_authorized_for_task(current_user, task),
            oob_subtasks=has_subtask
        )

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 9. TUNDA PEKERJAAN (PENDING DENGAN ALASAN WAJIB)
# =========================================================================
@tasks_bp.route('/<int:task_id>/pending', methods=['POST'])
@login_required
def mark_pending(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    reason = request.form.get('pending_reason', '').strip()
    if not reason:
        flash('Alasan penundaan pekerjaan wajib diisi.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    task.status = TaskStatus.PENDING
    task.pending_reason = reason

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "TASK_PENDING", f"Pekerjaan tertunda: {reason}")

        notify_all_admins(
            title=f"Tugas Tertunda: {task.title}",
            message=f"{current_user.name} menandai tugas '{task.title}' tertunda. Alasan: {reason}",
            target_url=f"/tasks/{task.id}"
        )
        flash('Status tugas berhasil diubah menjadi Tertunda.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal mengubah status tugas: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 10. LANJUTKAN TUGAS DARI PENDING KE IN_PROGRESS (RESUME)
# =========================================================================
@tasks_bp.route('/<int:task_id>/resume', methods=['POST'])
@login_required
def resume_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    task.status = TaskStatus.IN_PROGRESS
    task.pending_reason = None

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "TASK_RESUMED", "Pekerjaan dilanjutkan kembali.")
        flash('Tugas dilanjutkan kembali (Sedang Dikerjakan).', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal melanjutkan tugas: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 11. PENGAJUAN MULTI-ITEM MATERIAL (DYNAMIC FORM)
# =========================================================================
@tasks_bp.route('/<int:task_id>/request-items', methods=['POST'])
@login_required
def request_items(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    names = request.form.getlist('item_names[]') or request.form.getlist('item_names')
    qtys = request.form.getlist('quantities[]') or request.form.getlist('quantities')
    notes = request.form.getlist('notes[]') or request.form.getlist('notes')

    items_to_create = []
    for i in range(len(names)):
        n = names[i].strip() if i < len(names) else ''
        q = qtys[i].strip() if i < len(qtys) else ''
        nt = notes[i].strip() if i < len(notes) else ''
        if n and q:
            items_to_create.append((n, q, nt))

    if not items_to_create:
        flash('Minimal satu item material dengan nama dan kuantitas harus diisi.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    created_items = []
    for n, q, nt in items_to_create:
        item = ItemRequest(
            task_id=task.id,
            requested_by_id=current_user.id,
            item_name=n,
            quantity=q,
            notes=nt if nt else None,
            status=ItemStatus.REQUESTED
        )
        db.session.add(item)
        created_items.append(item)

    try:
        db.session.commit()
        summary_str = ", ".join(f"{it.item_name} ({it.quantity})" for it in created_items)
        log_activity(task.id, current_user.id, "MATERIAL_REQUESTED", f"Diajukan {len(created_items)} item: {summary_str}")

        notify_all_admins(
            title=f"Pengajuan Material Baru: {task.title}",
            message=f"{current_user.name} mengajukan {len(created_items)} item material untuk tugas '{task.title}': {summary_str}",
            target_url=f"/tasks/{task.id}"
        )
        flash(f'Berhasil mengajukan {len(created_items)} item material.', 'success')
        if request.headers.get('HX-Request'):
            return render_template(
                'tasks/_materials_section.html',
                task=task,
                item_requests=task.item_requests,
                ItemStatus=ItemStatus
            )
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menyimpan pengajuan material: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 12. PEMBATALAN PERMINTAAN MATERIAL OLEH STAF (STATUS REQUESTED)
# =========================================================================
@tasks_bp.route('/<int:task_id>/items/<int:item_id>/cancel', methods=['POST'])
@login_required
def cancel_item(task_id, item_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    item = db.session.get(ItemRequest, item_id)
    if not item or item.task_id != task.id:
        flash('Item material tidak ditemukan.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    if item.status != ItemStatus.REQUESTED:
        flash('Hanya item dengan status Diajukan yang dapat dibatalkan.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    item.status = ItemStatus.CANCELLED
    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "MATERIAL_CANCELLED", f"Permintaan material '{item.item_name}' dibatalkan oleh staf.")
        flash(f'Permintaan material "{item.item_name}" berhasil dibatalkan.', 'info')
        if request.headers.get('HX-Request'):
            return render_template(
                'tasks/_materials_section.html',
                task=task,
                item_requests=task.item_requests,
                ItemStatus=ItemStatus
            )
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal membatalkan permintaan material: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 13. KONFIRMASI PENERIMAAN MATERIAL (RECEIVED)
# =========================================================================
@tasks_bp.route('/<int:task_id>/items/<int:item_id>/receive', methods=['POST'])
@login_required
def receive_item(task_id, item_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    item = db.session.get(ItemRequest, item_id)
    if not item or item.task_id != task.id:
        flash('Item material tidak ditemukan.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    if item.status != ItemStatus.SHIPPED:
        flash('Hanya item dengan status Dikirim yang dapat dikonfirmasi penerimaannya.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    item.status = ItemStatus.RECEIVED
    item.received_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
        log_activity(task.id, current_user.id, "MATERIAL_RECEIVED", f"Material '{item.item_name}' ({item.quantity}) telah diterima di lapangan.")

        notify_all_admins(
            title=f"Material Diterima: {item.item_name}",
            message=f"{current_user.name} telah mengonfirmasi penerimaan '{item.item_name}' ({item.quantity}) untuk tugas '{task.title}'.",
            target_url=f"/tasks/{task.id}"
        )
        flash(f'Penerimaan material "{item.item_name}" berhasil dikonfirmasi.', 'success')
        if request.headers.get('HX-Request'):
            return render_template(
                'tasks/_materials_section.html',
                task=task,
                item_requests=task.item_requests,
                ItemStatus=ItemStatus
            )
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memperbarui status penerimaan: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))


# =========================================================================
# 14. PENGAJUAN REVIEW PENYELESAIAN TUGAS (DENGAN CATATAN OPSIONAL)
# =========================================================================
@tasks_bp.route('/<int:task_id>/submit-review', methods=['POST'])
@login_required
def submit_review(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('Tugas tidak ditemukan.', 'error')
        return redirect(url_for('tasks.index'))

    if not is_authorized_for_task(current_user, task):
        flash('Akses ditolak.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.TODO):
        flash('Hanya tugas yang sedang dikerjakan atau menunggu yang dapat diajukan untuk review.', 'error')
        return redirect(url_for('tasks.detail', task_id=task.id))

    remarks = request.form.get('completion_remarks', '').strip() or None

    task.status = TaskStatus.WAITING_REVIEW
    task.pending_reason = None
    task.review_notes = None
    task.completion_remarks = remarks

    try:
        db.session.commit()
        log_activity(
            task.id,
            current_user.id,
            "REVIEW_SUBMITTED",
            f"Pekerjaan diajukan untuk review. Catatan staf: {remarks if remarks else 'Tidak ada catatan.'}"
        )

        notify_all_admins(
            title=f"Review Diajukan: {task.title}",
            message=f"{current_user.name} telah mengajukan penyelesaian untuk tugas '{task.title}' dan menunggu evaluasi Administrator.",
            target_url="/admin/review-queue"
        )
        flash('Hasil pekerjaan berhasil diajukan untuk dievaluasi oleh Administrator.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal mengajukan review: {e}', 'error')

    return redirect(url_for('tasks.detail', task_id=task.id))
