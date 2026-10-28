import os
import sys
import re
import uuid
from datetime import datetime, timezone, date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import (
    User, Team, Task, SubTask, ItemRequest, TaskActivity, Notification,
    RoleEnum, TaskStatus, TaskPriority, ItemStatus, is_authorized_for_task
)
from app.extensions import db

print("======================================================================")
print("  TaskOps Enhanced Features & Modular Architecture Verification Suite  ")
print("======================================================================\n")


def get_csrf(client, url):
    res = client.get(url)
    match = re.search(r'name="csrf_token" value="([^"]+)"', res.get_data(as_text=True))
    assert match is not None, f"CSRF token not found on {url}"
    return match.group(1)


def login_client(username, password):
    c = app.test_client()
    csrf = get_csrf(c, '/auth/login')
    res = c.post('/auth/login', data={'identifier': username, 'password': password, 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200
    return c


# =========================================================================
# 1. Verifikasi Model Modular & Impor
# =========================================================================
print("--- [1/8] Verifikasi Arsitektur Model Modular ---")
from app.models.enums import RoleEnum as RE, TaskPriority as TP
from app.models.task import Task as TaskDirect
from app.models.user import User as UserDirect
from app.models.team import Team as TeamDirect
from app.models.subtask import SubTask as SubTaskDirect
from app.models.item_request import ItemRequest as ItemDirect
from app.models.activity import TaskActivity as ActDirect

assert TaskDirect is Task
assert UserDirect is User
assert TeamDirect is Team
assert SubTaskDirect is SubTask
assert ItemDirect is ItemRequest
assert ActDirect is TaskActivity
print("[OK] Seluruh model berhasil diimpor dari file modular masing-masing")


# =========================================================================
# 2. Bootstrapping Admin & VAPID Key Auto-Generation
# =========================================================================
print("\n--- [2/8] Verifikasi Auto-Admin & VAPID Key ---")
with app.app_context():
    admin = User.query.filter_by(role=RoleEnum.ADMIN).first()
    assert admin is not None, "Initial Admin must exist in DB"
    assert app.config.get('VAPID_PUBLIC_KEY') is not None
    assert app.config.get('VAPID_PRIVATE_KEY') is not None
    print(f"[OK] Admin terverifikasi: @{admin.username} & VAPID Key aktif")


# =========================================================================
# 3. Manajemen Tim & Pengguna
# =========================================================================
print("\n--- [3/8] Pembuatan Tim & Penugasan Staf Lapangan ---")
u_uid = uuid.uuid4().hex[:6]
staff_username = f"staf_mod_{u_uid}"
staff_phone = f"+62815{uuid.uuid4().int % 100000000:08d}"
team_name = f"Tim Elektrikal & Mekanikal {u_uid}"

c_admin = login_client('admin', 'AdminPassword123!')

# Buat Staf baru
csrf = get_csrf(c_admin, '/admin/users')
res_user = c_admin.post('/admin/users', data={
    'username': staff_username,
    'name': f'Budi Santoso {u_uid}',
    'phone_number': staff_phone,
    'password': 'StaffPassword123!',
    'role': RoleEnum.STAFF.value,
    'csrf_token': csrf
}, follow_redirects=True)
assert res_user.status_code == 200

# Buat Tim baru
csrf = get_csrf(c_admin, '/admin/teams')
res_team = c_admin.post('/admin/teams', data={
    'name': team_name,
    'description': 'Divisi pemeliharaan kelistrikan dan mekanik industri',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_team.status_code == 200

with app.app_context():
    staf_user = User.query.filter_by(username=staff_username).first()
    team_obj = Team.query.filter_by(name=team_name).first()
    assert staf_user is not None and team_obj is not None
    staf_id = staf_user.id
    team_id = team_obj.id

# Tetapkan Staf ke dalam Tim
csrf = get_csrf(c_admin, '/admin/teams')
res_assign = c_admin.post(
    f'/admin/teams/{team_id}/members',
    data={'member_ids': [str(staf_id)], 'csrf_token': csrf},
    follow_redirects=True
)
assert res_assign.status_code == 200
print(f"[OK] Tim '{team_name}' dibentuk dan staf @{staff_username} berhasil dimasukkan")


# =========================================================================
# 4. Batasan Wewenang Pembuatan Tugas (Admin vs Staff)
# =========================================================================
print("\n--- [4/8] Batasan Wewenang: Hanya Admin Bisa Buat Tugas ---")
c_staff = login_client(staff_username, 'StaffPassword123!')

# Staf mencoba membuat tugas -> harus ditolak / dialihkan
res_staff_create = c_staff.get('/tasks/create', follow_redirects=False)
assert res_staff_create.status_code in (302, 403), f"Staff should not access /tasks/create, got {res_staff_create.status_code}"

# Admin membuat tugas dengan prioritas GENTING (URGENT) dan menugaskannya ke Tim
task_title = f"Perbaikan Generator Darurat {u_uid}"
due_tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
csrf = get_csrf(c_admin, '/tasks/create')
res_task = c_admin.post('/tasks/create', data={
    'title': task_title,
    'description': 'Instruksi darurat: Cek oli, ganti filter solar, dan periksa busi pemantik.',
    'priority': TaskPriority.URGENT.value,
    'due_date': due_tomorrow,
    'assign_type': 'team',
    'assigned_team_id': str(team_id),
    'csrf_token': csrf
}, follow_redirects=True)
assert res_task.status_code == 200

with app.app_context():
    task = Task.query.filter_by(title=task_title).first()
    assert task is not None
    assert task.priority == TaskPriority.URGENT
    assert task.assigned_team_id == team_id
    assert task.is_archived is False
    assert task.is_overdue is False
    task_id = task.id

print("[OK] Wewenang diverifikasi: Staf ditolak di /tasks/create, Admin sukses membuat tugas URGENT untuk Tim")


# =========================================================================
# 5. Shared Team Checklist & Auto-Start
# =========================================================================
print("\n--- [5/8] Eksekusi Tugas oleh Staf (Shared Checklist & Blocker) ---")
# Staf melihat tugas tim di dasbor
res_dash = c_staff.get('/tasks/')
assert res_dash.status_code == 200
assert task_title in res_dash.get_data(as_text=True)

# Staf menambah subtask -> Status auto-advance ke IN_PROGRESS
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_sub1 = c_staff.post(f'/tasks/{task_id}/subtasks', data={
    'title': 'Kuras oli generator lama',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_sub1.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.IN_PROGRESS
    assert len(task.subtasks) == 1
    sub_id = task.subtasks[0].id

# Staf mencentang subtask
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/subtasks/{sub_id}/toggle', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    sub = db.session.get(SubTask, sub_id)
    assert sub.is_completed is True

# Staf menunda tugas (PENDING) dengan alasan kendala wajib
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_pend = c_staff.post(f'/tasks/{task_id}/pending', data={
    'pending_reason': 'Menunggu kunci pas khusus ukuran 24mm',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_pend.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.PENDING
    assert '24mm' in task.pending_reason

# Staf melanjutkan tugas (RESUME)
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_res = c_staff.post(f'/tasks/{task_id}/resume', data={'csrf_token': csrf}, follow_redirects=True)
assert res_res.status_code == 200
with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.pending_reason is None

print("[OK] Subtask checklist tim, transisi IN_PROGRESS, kendala PENDING & RESUME berhasil diverifikasi")


# =========================================================================
# 6. Alur Material: Pengajuan, Pembatalan oleh Staf, & Penolakan oleh Admin
# =========================================================================
print("\n--- [6/8] Alur Material: Pengajuan, Pembatalan Staf, & Penolakan Admin ---")
# Staf mengajukan 2 item material
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/request-items', data={
    'item_names[]': ['Filter Solar Donaldson', 'Oli Mesin Meditran SX 15W-40'],
    'quantities[]': ['2 pcs', '1 drum (200L)'],
    'notes[]': ['Part #P550388', 'Standar Pertamina'],
    'csrf_token': csrf
}, follow_redirects=True)

with app.app_context():
    items = ItemRequest.query.filter_by(task_id=task_id).all()
    assert len(items) == 2
    item_filter = next(i for i in items if 'Donaldson' in i.item_name)
    item_oli = next(i for i in items if 'Oli' in i.item_name)
    assert item_filter.status == ItemStatus.REQUESTED
    assert item_oli.status == ItemStatus.REQUESTED
    id_filter = item_filter.id
    id_oli = item_oli.id

# Staf membatalkan item Filter Solar (karena ternyata sudah ada di gudang lokal)
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_cancel = c_staff.post(f'/tasks/{task_id}/items/{id_filter}/cancel', data={'csrf_token': csrf}, follow_redirects=True)
assert res_cancel.status_code == 200
with app.app_context():
    it = db.session.get(ItemRequest, id_filter)
    assert it.status == ItemStatus.CANCELLED

# Admin menolak item Oli Mesin dengan alasan penolakan wajib
csrf = get_csrf(c_admin, '/admin/logistics')
res_reject = c_admin.post(f'/admin/logistics/{id_oli}/reject', data={
    'rejection_reason': 'Stok drum oli masih tersedia 3 drum di Workshop A.',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_reject.status_code == 200
with app.app_context():
    it = db.session.get(ItemRequest, id_oli)
    assert it.status == ItemStatus.REJECTED
    assert 'Workshop A' in it.rejection_reason

# Staf mengajukan item baru yang valid: Busi Pemantik
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/request-items', data={
    'item_names[]': ['Busi Pemantik NGK'],
    'quantities[]': ['4 pcs'],
    'notes[]': ['Tipe BPMR7A'],
    'csrf_token': csrf
}, follow_redirects=True)

with app.app_context():
    busi_item = ItemRequest.query.filter_by(task_id=task_id, item_name='Busi Pemantik NGK').first()
    assert busi_item is not None
    id_busi = busi_item.id

# Admin memesan & mengirim busi
csrf = get_csrf(c_admin, '/admin/logistics')
c_admin.post(f'/admin/logistics/{id_busi}/order', data={'csrf_token': csrf}, follow_redirects=True)
c_admin.post(f'/admin/logistics/{id_busi}/ship', data={'csrf_token': csrf}, follow_redirects=True)

# Staf mengonfirmasi penerimaan busi
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/items/{id_busi}/receive', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    it = db.session.get(ItemRequest, id_busi)
    assert it.status == ItemStatus.RECEIVED
    assert it.received_at is not None

print("[OK] Alur material lengkap: pembatalan staf, penolakan admin ber-alasan, dan siklus pesan-kirim-terima tuntas")


# =========================================================================
# 7. Pengajuan Review Selesai dengan Catatan Staf & Persetujuan Admin
# =========================================================================
print("\n--- [7/8] Review Penyelesaian Tugas & Catatan Remarks ---")
# Staf mengajukan review dengan catatan penyelesaian
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_rev = c_staff.post(f'/tasks/{task_id}/submit-review', data={
    'completion_remarks': 'Generator telah diuji beban 100kW selama 30 menit. Suhu dan tegangan stabil.',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_rev.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.WAITING_REVIEW
    assert '100kW' in task.completion_remarks

# Admin memeriksa dan menyetujui tugas
csrf = get_csrf(c_admin, '/admin/review-queue')
res_appr = c_admin.post(f'/admin/review-queue/{task_id}/approve', data={'csrf_token': csrf}, follow_redirects=True)
assert res_appr.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.COMPLETED

# Admin mengarsipkan tugas (Soft-Archive)
csrf = get_csrf(c_admin, f'/tasks/{task_id}')
res_arch = c_admin.post(f'/tasks/{task_id}/archive', data={'csrf_token': csrf}, follow_redirects=True)
assert res_arch.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.is_archived is True
    # Pastikan tugas tidak hilang dari DB (soft-archiving)
    assert db.session.get(Task, task_id) is not None

print("[OK] Review dengan catatan remarks staf, approval admin, dan soft-archiving berhasil 100%")


# =========================================================================
# 8. Halaman Profil & Cetak SPK
# =========================================================================
print("\n--- [8/8] Profil Pengguna & Pratinjau Cetak SPK ---")
# Cek Profil Staf
res_prof = c_staff.get('/auth/profile')
assert res_prof.status_code == 200
html_prof = res_prof.get_data(as_text=True)
import html
assert staff_username in html_prof
assert team_name in html.unescape(html_prof)

# Cek Cetak SPK
res_print = c_staff.get(f'/tasks/{task_id}/print')
assert res_print.status_code == 200
assert 'surat perintah kerja' in res_print.get_data(as_text=True).lower()

# Verifikasi Riwayat Aktivitas Audit Trail
with app.app_context():
    activities = TaskActivity.query.filter_by(task_id=task_id).all()
    assert len(activities) >= 5, f"Expected at least 5 audit activities, got {len(activities)}"
    actions = [a.action for a in activities]
    assert "TASK_CREATED" in actions
    assert "SUBTASK_ADDED" in actions
    assert "REVIEW_SUBMITTED" in actions
    assert "TASK_COMPLETED" in actions
    assert "TASK_ARCHIVED" in actions
    print(f"[OK] Audit trail mencatat {len(activities)} aktivitas historis secara berurutan")

print("\n======================================================================")
print("  >>> SELURUH PENGUJIAN FITUR & MODEL MODULAR BERHASIL 100%! <<<       ")
print("======================================================================\n")

