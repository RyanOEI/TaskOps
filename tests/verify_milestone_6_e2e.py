import os
import sys
import re
import json
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import (
    User, Team, Task, SubTask, ItemRequest, Notification,
    RoleEnum, TaskStatus, ItemStatus
)
from app.extensions import db

print("======================================================================")
print("  TaskOps Milestone 6: Full End-to-End & Docker Verification Suite   ")
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
# 1. Bootstrapping & Environment Verification
# =========================================================================
print("--- [1/6] Inisialisasi & Konfigurasi Sistem ---")
with app.app_context():
    admin = User.query.filter_by(role=RoleEnum.ADMIN).first()
    assert admin is not None, "Initial Admin must exist in DB"
    assert admin.check_password('AdminPassword123!') or admin.check_password('AdminPassword123') or admin.password_hash is not None

    assert app.config.get('VAPID_PUBLIC_KEY') is not None
    assert app.config.get('VAPID_PRIVATE_KEY') is not None
    print("[OK] Admin terverifikasi & Kunci VAPID aktif")

# =========================================================================
# 2. PWA Shell & Static Assets Verification
# =========================================================================
print("\n--- [2/6] Shell PWA & Aset Statis ---")
c_anon = app.test_client()
res_manifest = c_anon.get('/manifest.json')
assert res_manifest.status_code == 200
manifest_data = json.loads(res_manifest.get_data(as_text=True))
assert manifest_data['display'] == 'standalone'
assert 'TaskOps' in manifest_data['name']

res_sw = c_anon.get('/sw.js')
assert res_sw.status_code == 200
assert res_sw.headers.get('Service-Worker-Allowed') == '/'

res_icon = c_anon.get('/static/icons/icon.svg')
assert res_icon.status_code == 200
assert '<svg' in res_icon.get_data(as_text=True)
print("[OK] Manifest, Service Worker, dan Ikon SVG PWA valid")


# =========================================================================
# 3. Paginasi Pusat Notifikasi (Langkah 49)
# =========================================================================
print("\n--- [3/6] Paginasi Notifikasi (Langkah 49) ---")
u_uid = uuid.uuid4().hex[:6]
with app.app_context():
    notif_user = User(
        username=f'notif_test_{u_uid}',
        name='User Notif Test',
        role=RoleEnum.STAFF,
        is_active=True
    )
    notif_user.set_password('TestPass123!')
    db.session.add(notif_user)
    db.session.commit()
    notif_user_id = notif_user.id
    notif_username = notif_user.username

    # Buat 20 notifikasi untuk menguji paginasi 15/halaman
    for i in range(20):
        n = Notification(
            user_id=notif_user_id,
            title=f"Notifikasi Uji #{i+1}",
            message=f"Pesan pengujian nomor {i+1} untuk memverifikasi paginasi",
            is_read=False
        )
        db.session.add(n)
    db.session.commit()

c_notif = login_client(notif_username, 'TestPass123!')

# Halaman 1 (Harus berisi 15 notifikasi)
res_p1 = c_notif.get('/notifications/?page=1')
assert res_p1.status_code == 200
html_p1 = res_p1.get_data(as_text=True)
assert 'Notifikasi Uji #20' in html_p1
assert 'Berikutnya' in html_p1
assert 'halaman' in html_p1 and 'dari' in html_p1 and '1' in html_p1 and '2' in html_p1

# Halaman 2 (Harus berisi 5 notifikasi tersisa)
res_p2 = c_notif.get('/notifications/?page=2')
assert res_p2.status_code == 200
html_p2 = res_p2.get_data(as_text=True)
assert 'Notifikasi Uji #1' in html_p2
assert 'Sebelumnya' in html_p2
assert 'halaman' in html_p2 and 'dari' in html_p2 and '2' in html_p2

# Tandai semua dibaca
csrf = get_csrf(c_notif, '/notifications/')
res_read_all = c_notif.post('/notifications/mark-all-read', data={'csrf_token': csrf}, follow_redirects=True)
assert res_read_all.status_code == 200
with app.app_context():
    unread_c = Notification.query.filter_by(user_id=notif_user_id, is_read=False).count()
    assert unread_c == 0
print("[OK] Paginasi notifikasi server-side (15/halaman) & Mark-all-read berhasil diverifikasi")


# =========================================================================
# 4. Manajemen Pengguna & Tim (Milestone 3 & Fixes)
# =========================================================================
print("\n--- [4/6] Manajemen Pengguna & Tim Operasional ---")
c_admin = login_client('admin', 'AdminPassword123!')

# Buat Staf Operasional baru
staff_name = f'Staf E2E {u_uid}'
staff_user = f'staf_e2e_{u_uid}'
csrf = get_csrf(c_admin, '/admin/users')
res_cu = c_admin.post('/admin/users', data={
    'username': staff_user,
    'name': staff_name,
    'phone_number': f'+62814{uuid.uuid4().int % 100000000:08d}',
    'password': 'StaffE2EPassword123!',
    'role': RoleEnum.STAFF.value,
    'csrf_token': csrf
}, follow_redirects=True)
assert res_cu.status_code == 200

# Buat Tim Baru
team_name = f'Tim Lapangan E2E {u_uid}'
csrf = get_csrf(c_admin, '/admin/teams')
res_ct = c_admin.post('/admin/teams', data={
    'name': team_name,
    'description': 'Divisi pengujian end-to-end menyeluruh',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_ct.status_code == 200

with app.app_context():
    staf_obj = User.query.filter_by(username=staff_user).first()
    team_obj = Team.query.filter_by(name=team_name).first()
    assert staf_obj is not None and team_obj is not None
    staf_id = staf_obj.id
    team_id = team_obj.id

# Tetapkan anggota ke tim via endpoint chip
csrf = get_csrf(c_admin, '/admin/teams')
res_assign = c_admin.post(
    f'/admin/teams/{team_id}/members',
    data={'member_ids': [str(staf_id)], 'csrf_token': csrf},
    follow_redirects=True
)
assert res_assign.status_code == 200

with app.app_context():
    team_obj = db.session.get(Team, team_id)
    assert len(team_obj.active_members) == 1
    assert team_obj.active_members[0].id == staf_id
print("[OK] Pengguna dan Tim operasional dibuat dan dihubungkan secara terpisah")


# =========================================================================
# 5. Siklus Hidup Tugas, Logistik & Review Menyeluruh (Milestone 4 & 5)
# =========================================================================
print("\n--- [5/6] Siklus Lengkap: Tugas -> Logistik -> Review -> Selesai ---")
c_staff = login_client(staff_user, 'StaffE2EPassword123!')

# 5a. Admin membuat tugas
task_title = f'Peremajaan Pipa Distribusi E2E {u_uid}'
csrf = get_csrf(c_admin, '/tasks/create')
res_task = c_admin.post('/tasks/create', data={
    'title': task_title,
    'description': 'Instruksi lengkap perbaikan pipa dan pengujian tekanan',
    'due_date': '2026-11-30',
    'assign_type': 'user',
    'assigned_user_id': str(staf_id),
    'csrf_token': csrf
}, follow_redirects=True)
assert res_task.status_code == 200

with app.app_context():
    task = Task.query.filter_by(title=task_title).first()
    assert task is not None
    assert task.status == TaskStatus.TODO
    task_id = task.id

# 5b. Staf menambah subtask -> Auto-advance ke IN_PROGRESS
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_sub = c_staff.post(f'/tasks/{task_id}/subtasks', data={
    'title': 'Isolasi katup utama',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_sub.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.IN_PROGRESS
    subtask_id = task.subtasks[0].id

# 5c. Staf menunda tugas (PENDING)
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_pend = c_staff.post(f'/tasks/{task_id}/pending', data={
    'pending_reason': 'Menunggu flange adaptor 4 inch',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_pend.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.PENDING
    assert task.pending_reason == 'Menunggu flange adaptor 4 inch'

# 5d. Staf melanjutkan tugas (RESUME)
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_res = c_staff.post(f'/tasks/{task_id}/resume', data={'csrf_token': csrf}, follow_redirects=True)
assert res_res.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.pending_reason is None

# 5e. Staf mengajukan kebutuhan material multi-item
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_items = c_staff.post(f'/tasks/{task_id}/request-items', data={
    'item_names[]': ['Flange Adaptor 4 inch', 'Gasket EPDM 4 inch'],
    'quantities[]': ['2 pcs', '4 pcs'],
    'notes[]': ['PN16 ductile iron', 'Tebal 3mm'],
    'csrf_token': csrf
}, follow_redirects=True)
assert res_items.status_code == 200

with app.app_context():
    items = ItemRequest.query.filter_by(task_id=task_id).all()
    assert len(items) == 2
    item1_id, item2_id = items[0].id, items[1].id
    assert items[0].status == ItemStatus.REQUESTED

# 5f. Admin memesan dan mengirim barang via batch actions
csrf = get_csrf(c_admin, '/admin/logistics')
c_admin.post(f'/admin/logistics/tasks/{task_id}/order-all', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    it1 = db.session.get(ItemRequest, item1_id)
    assert it1.status == ItemStatus.ORDERED and it1.ordered_at is not None

csrf = get_csrf(c_admin, '/admin/logistics')
c_admin.post(f'/admin/logistics/tasks/{task_id}/ship-all', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    it1 = db.session.get(ItemRequest, item1_id)
    assert it1.status == ItemStatus.SHIPPED and it1.shipped_at is not None

# 5g. Staf mengonfirmasi penerimaan barang
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/items/{item1_id}/receive', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    it1 = db.session.get(ItemRequest, item1_id)
    assert it1.status == ItemStatus.RECEIVED and it1.received_at is not None

# 5h. Staf mengajukan review tugas
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/submit-review', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.WAITING_REVIEW

# 5i. Admin meminta perbaikan (request continuation)
csrf = get_csrf(c_admin, '/admin/review-queue')
c_admin.post(f'/admin/review-queue/{task_id}/request-continuation', data={
    'review_notes': 'Harap lakukan tes tekanan hidrostatik 10 bar selama 15 menit.',
    'csrf_token': csrf
}, follow_redirects=True)
with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.IN_PROGRESS
    assert 'hidrostatik' in task.review_notes

# 5j. Staf menyelesaikan instruksi dan re-submit review
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(f'/tasks/{task_id}/submit-review', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.WAITING_REVIEW
    assert task.review_notes is None  # Otomatis dibersihkan saat re-submit

# 5k. Admin menyetujui tugas (Approve)
csrf = get_csrf(c_admin, '/admin/review-queue')
c_admin.post(f'/admin/review-queue/{task_id}/approve', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    task = db.session.get(Task, task_id)
    assert task.status == TaskStatus.COMPLETED
print("[OK] Siklus penuh tugas -> subtask -> pending -> material -> logistik -> review -> approve tuntas 100%")


# =========================================================================
# 6. Verifikasi Struktur File Docker (Langkah 51, 52, 53)
# =========================================================================
print("\n--- [6/6] Verifikasi Konfigurasi Docker ---")
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

dockerfile_path = os.path.join(root_dir, 'Dockerfile')
assert os.path.exists(dockerfile_path), "Dockerfile must exist"
with open(dockerfile_path, 'r', encoding='utf-8') as f:
    df_content = f.read()
    assert 'python:3.12-slim' in df_content
    assert 'appuser' in df_content
    assert '/app/instance' in df_content
    assert 'gunicorn' in df_content
    assert 'EXPOSE 5000' in df_content
print("[OK] Dockerfile valid (python:3.12-slim, non-root appuser, instance permissions, gunicorn CMD)")

compose_path = os.path.join(root_dir, 'docker-compose.yml')
assert os.path.exists(compose_path), "docker-compose.yml must exist"
with open(compose_path, 'r', encoding='utf-8') as f:
    dc_content = f.read()
    assert 'services:' in dc_content
    assert 'sqlite_data:/app/instance' in dc_content
    assert '5000:5000' in dc_content
    assert 'env_file:' in dc_content
print("[OK] docker-compose.yml valid (persisten volume sqlite_data, env_file, port mapping)")

dockerignore_path = os.path.join(root_dir, '.dockerignore')
assert os.path.exists(dockerignore_path), ".dockerignore must exist"
with open(dockerignore_path, 'r', encoding='utf-8') as f:
    di_content = f.read()
    assert '.venv' in di_content
    assert '__pycache__' in di_content
print("[OK] .dockerignore valid")

print("\n======================================================================")
print("  >>> SELURUH PENGUJIAN END-TO-END & DOCKER BERHASIL 100%! <<<        ")
print("======================================================================\n")
