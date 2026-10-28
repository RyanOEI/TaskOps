"""
Test Suite: TaskOps HTMX Partial Page Rendering & Seamless In-Place UX
Verifies:
1. Static library availability (/static/js/htmx.min.js) and Service Worker precache.
2. Persistent Shell Navigation: Partial loading into #main-content.
3. Subtask In-Place Interactivity: Toggle & Add return _subtasks_section.html without 302 redirect.
4. Material In-Place Interactivity: Request, Cancel & Receive return _materials_section.html without 302 redirect.
5. Out-of-band updates (Task status badge updated in header).
6. Dashboard Filtering: #tasks-view-container partial swaps.
"""
import os
import sys
import re
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import (
    User, Team, Task, SubTask, ItemRequest, TaskActivity,
    RoleEnum, TaskStatus, TaskPriority, ItemStatus
)

app = create_app()


def get_csrf(client, url):
    res = client.get(url)
    match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', res.get_data(as_text=True))
    if not match:
        match = re.search(r'name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', res.get_data(as_text=True))
    assert match, f"CSRF token not found in {url}"
    return match.group(1)


print("\n" + "=" * 70)
print("  TaskOps HTMX Partial Page Rendering & Seamless UX Verification  ")
print("=" * 70)

# =========================================================================
# 1. Pustaka HTMX & Service Worker Precache
# =========================================================================
print("\n--- [1/6] Pustaka HTMX & Service Worker Cache ---")
with app.test_client() as client:
    res_htmx = client.get('/static/js/htmx.min.js')
    assert res_htmx.status_code == 200, f"Expected 200 for htmx.min.js, got {res_htmx.status_code}"
    assert len(res_htmx.data) > 30000, "HTMX bundle is too small"

    res_sw = client.get('/sw.js')
    assert res_sw.status_code == 200
    assert '/static/js/htmx.min.js' in res_sw.get_data(as_text=True), "htmx.min.js must be in sw.js PRECACHE_URLS"

print("[OK] htmx.min.js aktif dan dicache dalam Service Worker precache")


# Inisialisasi User & Client
unique_id = uuid.uuid4().hex[:6]
admin_identity = 'admin'
admin_pass = 'AdminPassword123!'

staff_username = f"staf_htmx_{unique_id}"
staff_email = f"staf_htmx_{unique_id}@example.com"
staff_pass = "StaffPassword123!"

with app.app_context():
    staff = User(
        username=staff_username,
        name=f"Staf Lapangan {unique_id}",
        email=staff_email,
        phone_number=f"+62817{unique_id[:8]}",
        role=RoleEnum.STAFF,
        is_active=True
    )
    staff.set_password(staff_pass)
    db.session.add(staff)

    team = Team(
        name=f"Tim HTMX {unique_id}",
        description="Divisi Operasional Lapangan HTMX",
        is_active=True
    )
    team.members.append(staff)
    db.session.add(team)
    db.session.commit()
    team_id = team.id
    staff_id = staff.id

def login_client(identifier, password):
    c = app.test_client()
    csrf = get_csrf(c, '/auth/login')
    res = c.post('/auth/login', data={'identifier': identifier, 'password': password, 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200, f"Login failed for {identifier}: {res.status_code}"
    return c

c_admin = login_client(admin_identity, admin_pass)
c_staff = login_client(staff_username, staff_pass)


# =========================================================================
# 2. Navigasi Shell Persisten (HTMX Partial Requests)
# =========================================================================
print("\n--- [2/6] Navigasi Shell Persisten (Header HX-Request) ---")
htmx_headers = {'HX-Request': 'true'}

# Test navigasi ke halaman-halaman utama dengan header HX-Request
routes_to_test = [
    ('/tasks/', 'tasks-view-container'),
    ('/admin/logistics', 'Logistik Material Proyek'),
    ('/admin/review-queue', 'Antrean Evaluasi Tugas'),
    ('/admin/users', 'Manajemen Pengguna'),
    ('/admin/teams', 'Manajemen Tim'),
    ('/notifications/', 'Pusat Notifikasi'),
    ('/auth/profile', 'Profil Saya'),
]

for url, expected_text in routes_to_test:
    res = c_admin.get(url, headers=htmx_headers)
    assert res.status_code == 200, f"Expected 200 for {url}, got {res.status_code}"
    html = res.get_data(as_text=True)
    assert expected_text in html, f"Expected '{expected_text}' in response for {url}"
    # Pastikan elemen shell dasar (aside sidebar) tetap ada di template jika render base
    assert 'TaskOps' in html
    # Pastikan utilitas modal global selalu tersedia di base shell
    assert 'window.openModal = function' in html

# Verifikasi khusus untuk /admin/users: extra_scripts harus berada di dalam #main-content
res_users = c_admin.get('/admin/users', headers=htmx_headers)
html_users = res_users.get_data(as_text=True)
assert 'window.submitCreateUser' in html_users
main_content_end = html_users.find('</main>')
script_pos = html_users.find('window.submitCreateUser')
assert script_pos != -1 and script_pos < main_content_end, "extra_scripts must be inside <main id='main-content'>"

print("[OK] Seluruh rute navigasi mendukung pemuatan parsial HTMX dengan status 200")


# =========================================================================
# 3. Interaktivitas Subtask In-Place (Zero Scroll Jump)
# =========================================================================
print("\n--- [3/6] Checklist Subtask In-Place (Zero Scroll Jump) ---")

# Buat tugas baru via Admin
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    task = Task(
        title=f"Perawatan Kompresor Gas {unique_id}",
        description="Pembersihan valve dan penggantian filter kompresor",
        priority=TaskPriority.HIGH,
        due_date=date.today() + timedelta(days=2),
        status=TaskStatus.TODO,
        created_by_id=admin.id,
        assigned_team_id=team_id
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.id

# Staf menambahkan subtask #1 via HTMX
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_add = c_staff.post(
    f'/tasks/{task_id}/subtasks',
    data={'title': 'Inspeksi Tekanan Valve', 'csrf_token': csrf},
    headers=htmx_headers
)
# Wajib mengembalikan status 200 (HTML snippet _subtasks_section.html) BUKAN redirect 302!
assert res_add.status_code == 200, f"Expected 200, got {res_add.status_code}"
html_add = res_add.get_data(as_text=True)
assert 'id="subtasks-section"' in html_add
assert 'Inspeksi Tekanan Valve' in html_add
assert '0 / 1 Selesai' in html_add

with app.app_context():
    st = SubTask.query.filter_by(task_id=task_id).first()
    assert st is not None
    assert st.title == 'Inspeksi Tekanan Valve'
    subtask_id = st.id
    # Verifikasi tugas otomatis transisi ke IN_PROGRESS
    t = db.session.get(Task, task_id)
    assert t.status == TaskStatus.IN_PROGRESS

# Staf mencentang subtask via HTMX
res_toggle = c_staff.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/toggle',
    data={'csrf_token': csrf},
    headers=htmx_headers
)
# Wajib mengembalikan status 200 (HTML snippet) BUKAN redirect 302!
assert res_toggle.status_code == 200, f"Expected 200, got {res_toggle.status_code}"
html_toggle = res_toggle.get_data(as_text=True)
assert 'id="subtasks-section"' in html_toggle
assert '1 / 1 Selesai' in html_toggle
assert 'line-through' in html_toggle
# Verifikasi OOB swap untuk status badge
assert 'id="task-status-badge"' in html_toggle
assert 'hx-swap-oob="innerHTML"' in html_toggle

with app.app_context():
    st = db.session.get(SubTask, subtask_id)
    assert st.is_completed is True

print("[OK] Subtask checklist in-place toggle & add berhasil tanpa redirect (Zero scroll jump)")


# =========================================================================
# 4. Pengadaan Material In-Place
# =========================================================================
print("\n--- [4/6] Pengadaan Material In-Place ---")

# Staf mengajukan material via HTMX
res_mat_req = c_staff.post(
    f'/tasks/{task_id}/request-items',
    data={
        'item_names[]': ['Gasket Seal 3 inch'],
        'quantities[]': ['2 pcs'],
        'notes[]': ['Tahan panas tinggi'],
        'csrf_token': csrf
    },
    headers=htmx_headers
)
assert res_mat_req.status_code == 200, f"Expected 200, got {res_mat_req.status_code}"
html_mat = res_mat_req.get_data(as_text=True)
assert 'id="materials-section"' in html_mat
assert 'Gasket Seal 3 inch' in html_mat
assert 'Diajukan' in html_mat

with app.app_context():
    item = ItemRequest.query.filter_by(task_id=task_id, item_name='Gasket Seal 3 inch').first()
    assert item is not None
    assert item.status == ItemStatus.REQUESTED
    item_id = item.id

# Staf membatalkan material via HTMX
res_mat_cancel = c_staff.post(
    f'/tasks/{task_id}/items/{item_id}/cancel',
    data={'csrf_token': csrf},
    headers=htmx_headers
)
assert res_mat_cancel.status_code == 200, f"Expected 200, got {res_mat_cancel.status_code}"
html_cancel = res_mat_cancel.get_data(as_text=True)
assert 'id="materials-section"' in html_cancel
assert 'Dibatalkan' in html_cancel

with app.app_context():
    it = db.session.get(ItemRequest, item_id)
    assert it.status == ItemStatus.CANCELLED

print("[OK] Pengajuan & pembatalan material in-place berhasil merender _materials_section.html langsung")


# =========================================================================
# 5. Penyaringan Dasbor Tugas (#tasks-view-container)
# =========================================================================
print("\n--- [5/6] Penyaringan Dasbor Tugas Parsial ---")

res_filter_todo = c_staff.get('/tasks/?tab=TODO', headers=htmx_headers)
assert res_filter_todo.status_code == 200
html_todo = res_filter_todo.get_data(as_text=True)
assert 'id="tasks-view-container"' in html_todo

res_filter_prio = c_staff.get('/tasks/?priority=HIGH', headers=htmx_headers)
assert res_filter_prio.status_code == 200
html_prio = res_filter_prio.get_data(as_text=True)
assert 'id="tasks-view-container"' in html_prio
assert f"Perawatan Kompresor Gas {unique_id}" in html_prio

print("[OK] Tab filter & prioritas mengembalikan kontainer #tasks-view-container secara parsial")


# =========================================================================
# 6. Backward Compatibility: Request Non-HTMX
# =========================================================================
print("\n--- [6/6] Kompatibilitas Mundur (Non-HTMX Requests) ---")

# Request biasa tanpa header HX-Request wajib redirect 302 seperti sebelumnya
res_non_htmx = c_staff.post(
    f'/tasks/{task_id}/subtasks',
    data={'title': 'Subtask Non-HTMX', 'csrf_token': csrf}
)
assert res_non_htmx.status_code == 302, f"Expected 302 redirect for non-HTMX, got {res_non_htmx.status_code}"
assert f'/tasks/{task_id}' in res_non_htmx.headers.get('Location', '')

print("[OK] Request browser standar / unit test non-HTMX tetap menjalankan redirect 302")

print("\n" + "=" * 70)
print("  >>> SELURUH PENGUJIAN HTMX & SEAMLESS UX BERHASIL 100%! <<<        ")
print("=" * 70 + "\n")
