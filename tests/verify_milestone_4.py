import os
import sys
import re
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import (
    User, Team, Task, SubTask, ItemRequest, Notification,
    RoleEnum, TaskStatus, ItemStatus
)
from app.extensions import db

print("Starting Milestone 4 Verification Suite...")


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


# 0. Setup isolated test users and teams
with app.app_context():
    # Staff 1 (Pelaksana Tugas)
    u_uid = uuid.uuid4().hex[:6]
    staff1 = User(
        username=f'staff1_{u_uid}',
        name='Staf Pelaksana Satu',
        phone_number=f'+62811{uuid.uuid4().int % 100000000:08d}',
        role=RoleEnum.STAFF,
        is_active=True
    )
    staff1.set_password('StaffPass123!')
    db.session.add(staff1)

    # Staff 2 (Staf Lain di Luar Tugas)
    staff2 = User(
        username=f'staff2_{u_uid}',
        name='Staf Lain Luar',
        phone_number=f'+62812{uuid.uuid4().int % 100000000:08d}',
        role=RoleEnum.STAFF,
        is_active=True
    )
    staff2.set_password('StaffPass123!')
    db.session.add(staff2)

    # Tim Operasional M4
    team_ops = Team(
        name=f'Tim Instalasi M4 {u_uid}',
        description='Divisi instalasi teknis Milestone 4',
        is_active=True
    )
    team_ops.members.append(staff1)
    db.session.add(team_ops)

    db.session.commit()

    staff1_id = staff1.id
    staff1_user = staff1.username
    staff2_id = staff2.id
    staff2_user = staff2.username
    team_ops_id = team_ops.id
    team_ops_name = team_ops.name

c_admin = login_client('admin', 'AdminPassword123!')
c_staff1 = login_client(staff1_user, 'StaffPass123!')
c_staff2 = login_client(staff2_user, 'StaffPass123!')

print("[OK] Test environment, users, and clients initialized")


# =========================================================================
# 1. Step 29 & 30: Task Creation (Admin Only) & Notifications (Step 31)
# =========================================================================
# 1a. Non-admin blocked from /tasks/create
res_blocked = c_staff1.get('/tasks/create', follow_redirects=False)
assert res_blocked.status_code == 302 and '/tasks/' in res_blocked.headers['Location']
print("[OK] Access control verified: Non-admin is blocked from /tasks/create")

# 1b. Admin creates task assigned to user (staff1)
csrf = get_csrf(c_admin, '/tasks/create')
task_user_title = f'Instalasi Genset M4 {uuid.uuid4().hex[:6]}'
res = c_admin.post('/tasks/create', data={
    'title': task_user_title,
    'description': 'Lakukan instalasi kabel feeder dan panel otomatis ATS genset',
    'due_date': '2026-12-31',
    'assign_type': 'user',
    'assigned_user_id': str(staff1_id),
    'csrf_token': csrf
}, follow_redirects=False)
assert res.status_code == 302
task_user_url = res.headers['Location']

with app.app_context():
    task_user = Task.query.filter_by(title=task_user_title).first()
    assert task_user is not None
    assert task_user.status == TaskStatus.TODO
    assert task_user.assigned_user_id == staff1_id
    assert task_user.assigned_team_id is None
    task_user_id = task_user.id

    # Verifikasi notifikasi terkirim ke staff1
    notif = Notification.query.filter_by(user_id=staff1_id).order_by(Notification.created_at.desc()).first()
    assert notif is not None
    assert task_user_title in notif.message
    print("[OK] Verified: Task assigned to user created with status TODO and in-app notification sent")

# 1c. Admin creates task assigned to team (team_ops)
csrf = get_csrf(c_admin, '/tasks/create')
task_team_title = f'Pembersihan Saluran Pendingin {uuid.uuid4().hex[:6]}'
res = c_admin.post('/tasks/create', data={
    'title': task_team_title,
    'description': 'Pembersihan pipa chiller dan drainase',
    'assign_type': 'team',
    'assigned_team_id': str(team_ops_id),
    'csrf_token': csrf
}, follow_redirects=False)
assert res.status_code == 302

with app.app_context():
    task_team = Task.query.filter_by(title=task_team_title).first()
    assert task_team is not None
    assert task_team.assigned_team_id == team_ops_id
    task_team_id = task_team.id

    # Verifikasi seluruh anggota tim (staff1) menerima notifikasi
    notif = Notification.query.filter_by(user_id=staff1_id).order_by(Notification.created_at.desc()).first()
    assert notif is not None
    assert task_team_title in notif.message
    print("[OK] Verified: Task assigned to team created and team members notified")


# =========================================================================
# 2. Step 32 & 33: My Tasks Scoping & Dashboard Tabs
# =========================================================================
# staff1 should see task_user and task_team
res_dash_s1 = c_staff1.get('/tasks/')
assert res_dash_s1.status_code == 200
html_s1 = res_dash_s1.get_data(as_text=True)
assert task_user_title in html_s1
assert task_team_title in html_s1

# staff2 should NOT see either task
res_dash_s2 = c_staff2.get('/tasks/')
assert res_dash_s2.status_code == 200
html_s2 = res_dash_s2.get_data(as_text=True)
assert task_user_title not in html_s2
assert task_team_title not in html_s2

# Admin should see both tasks
res_dash_adm = c_admin.get('/tasks/')
assert res_dash_adm.status_code == 200
html_adm = res_dash_adm.get_data(as_text=True)
assert task_user_title in html_adm
assert task_team_title in html_adm
print("[OK] Verified: Dashboard scoping (staff sees assigned tasks/team tasks, unauthorized staff sees none, admin sees all)")


# =========================================================================
# 3. Step 34 & 35: Task Detail Authorization
# =========================================================================
# staff2 (unauthorized) blocked from viewing task_user
res_s2_detail = c_staff2.get(f'/tasks/{task_user_id}', follow_redirects=False)
assert res_s2_detail.status_code == 302 and '/tasks/' in res_s2_detail.headers['Location']

# staff1 can view task_user detail
res_s1_detail = c_staff1.get(f'/tasks/{task_user_id}')
assert res_s1_detail.status_code == 200
assert task_user_title in res_s1_detail.get_data(as_text=True)
print("[OK] Verified: Detail view authorization (unauthorized blocked, assigned staff allowed)")


# =========================================================================
# 4. Step 36: Subtask Creation & Auto-Advance Status (TODO -> IN_PROGRESS)
# =========================================================================
# Unauthorized staff2 cannot add subtask
csrf_s2 = get_csrf(c_staff2, '/tasks/')
res_sub_unauth = c_staff2.post(
    f'/tasks/{task_user_id}/subtasks',
    data={'title': 'Hacker Subtask', 'csrf_token': csrf_s2},
    follow_redirects=False
)
assert res_sub_unauth.status_code in (302, 403)

# staff1 adds subtask 1
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_sub1 = c_staff1.post(f'/tasks/{task_user_id}/subtasks', data={
    'title': 'Cek grounding panel genset',
    'csrf_token': csrf
}, follow_redirects=True)
assert res_sub1.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_user_id)
    assert len(task.subtasks) == 1
    assert task.subtasks[0].title == 'Cek grounding panel genset'
    assert task.subtasks[0].is_completed is False
    # Auto-advance status check:
    assert task.status == TaskStatus.IN_PROGRESS, f"Expected IN_PROGRESS, got {task.status}"
    subtask_id = task.subtasks[0].id
    print("[OK] Verified: Adding subtask auto-advances task from TODO to IN_PROGRESS")

# Toggle subtask completion
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_toggle = c_staff1.post(f'/tasks/{task_user_id}/subtasks/{subtask_id}/toggle', data={'csrf_token': csrf}, follow_redirects=True)
assert res_toggle.status_code == 200

with app.app_context():
    st = db.session.get(SubTask, subtask_id)
    assert st.is_completed is True
    print("[OK] Verified: Subtask toggle marks is_completed=True")


# =========================================================================
# 5. Step 37 & 38: Mark Task as PENDING & Resume Flow
# =========================================================================
# 5a. Mark PENDING requires reason
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_empty_pend = c_staff1.post(f'/tasks/{task_user_id}/pending', data={'pending_reason': '', 'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    task = db.session.get(Task, task_user_id)
    assert task.status == TaskStatus.IN_PROGRESS  # Not changed

# 5b. Mark PENDING with valid reason
reason_text = "Menunggu pengiriman kabel tembaga 50mm dan breaker 200A"
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_pend = c_staff1.post(f'/tasks/{task_user_id}/pending', data={
    'pending_reason': reason_text,
    'csrf_token': csrf
}, follow_redirects=True)
assert res_pend.status_code == 200
html_pend = res_pend.get_data(as_text=True)
assert 'Pekerjaan Sedang Tertunda' in html_pend
assert reason_text in html_pend

with app.app_context():
    task = db.session.get(Task, task_user_id)
    assert task.status == TaskStatus.PENDING
    assert task.pending_reason == reason_text

    # Verifikasi notifikasi terkirim ke Admin
    admin_user = User.query.filter_by(username='admin').first()
    admin_notif = Notification.query.filter_by(user_id=admin_user.id).order_by(Notification.created_at.desc()).first()
    assert admin_notif is not None
    assert 'Tertunda' in admin_notif.title
    print("[OK] Verified: Marking task PENDING sets status, saves reason, shows amber banner, and notifies admins")

# 5c. Resume task from PENDING
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_res = c_staff1.post(f'/tasks/{task_user_id}/resume', data={'csrf_token': csrf}, follow_redirects=True)
assert res_res.status_code == 200

with app.app_context():
    task = db.session.get(Task, task_user_id)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.pending_reason is None
    print("[OK] Verified: Resuming task returns status to IN_PROGRESS and clears pending_reason")

# 5d. Also verify subtask action auto-clears PENDING to IN_PROGRESS
# Set back to PENDING
task_user_obj = None
with app.app_context():
    task = db.session.get(Task, task_user_id)
    task.status = TaskStatus.PENDING
    task.pending_reason = "Alasan sementara"
    db.session.commit()

# Add a subtask while PENDING -> auto resume to IN_PROGRESS
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
c_staff1.post(f'/tasks/{task_user_id}/subtasks', data={
    'title': 'Pasang busbar tembaga',
    'csrf_token': csrf
}, follow_redirects=True)

with app.app_context():
    task = db.session.get(Task, task_user_id)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.pending_reason is None
    print("[OK] Verified: Adding subtask while PENDING auto-resumes task to IN_PROGRESS and clears reason")


# =========================================================================
# 6. Step 40: Multi-Item Material Request (Dynamic Form)
# =========================================================================
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_items = c_staff1.post(
    f'/tasks/{task_user_id}/request-items',
    data={
        'item_names[]': ['Kabel NYY 4x50mm', 'MCCB 200A 3P', 'Skun Kabel 50mm'],
        'quantities[]': ['50 meter', '1 unit', '12 buah'],
        'notes[]': ['Supreme / Kabelmetal', 'Schneider NSX250F', 'Tembaga lapis timah'],
        'csrf_token': csrf
    },
    follow_redirects=True
)
assert res_items.status_code == 200
html_items = res_items.get_data(as_text=True)
assert 'Kabel NYY 4x50mm' in html_items
assert 'MCCB 200A 3P' in html_items
assert 'Skun Kabel 50mm' in html_items

with app.app_context():
    items = ItemRequest.query.filter_by(task_id=task_user_id).all()
    assert len(items) == 3
    for it in items:
        assert it.status == ItemStatus.REQUESTED
        assert it.requested_by_id == staff1_id
    first_item_id = items[0].id

    # Verifikasi notifikasi material ke Admin
    admin_user = User.query.filter_by(username='admin').first()
    notif_mat = Notification.query.filter_by(user_id=admin_user.id).order_by(Notification.created_at.desc()).first()
    assert notif_mat is not None
    assert 'Pengajuan Material Baru' in notif_mat.title
    print("[OK] Verified: Dynamic multi-item material request successfully created 3 ItemRequests (REQUESTED) and notified admins")


# =========================================================================
# 7. Step 41: Mark Item RECEIVED
# =========================================================================
# Simulate item status being SHIPPED by logistics (admin)
with app.app_context():
    item_to_ship = db.session.get(ItemRequest, first_item_id)
    item_to_ship.status = ItemStatus.SHIPPED
    item_to_ship.shipped_at = datetime.now(timezone.utc)
    db.session.commit()

# staff1 marks item as RECEIVED
csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_rcv = c_staff1.post(f'/tasks/{task_user_id}/items/{first_item_id}/receive', data={'csrf_token': csrf}, follow_redirects=True)
assert res_rcv.status_code == 200

with app.app_context():
    item_rcv = db.session.get(ItemRequest, first_item_id)
    assert item_rcv.status == ItemStatus.RECEIVED
    assert item_rcv.received_at is not None

    # Verifikasi notifikasi penerimaan ke admin
    admin_user = User.query.filter_by(username='admin').first()
    notif_rcv = Notification.query.filter_by(user_id=admin_user.id).order_by(Notification.created_at.desc()).first()
    assert notif_rcv is not None
    assert 'Material Diterima' in notif_rcv.title
    print("[OK] Verified: Marking item RECEIVED sets status, stamps received_at, and notifies admins")

# Verify that non-shipped items cannot be received
with app.app_context():
    items = ItemRequest.query.filter_by(task_id=task_user_id).all()
    requested_item_id = [it.id for it in items if it.status == ItemStatus.REQUESTED][0]

csrf = get_csrf(c_staff1, f'/tasks/{task_user_id}')
res_bad_rcv = c_staff1.post(f'/tasks/{task_user_id}/items/{requested_item_id}/receive', data={'csrf_token': csrf}, follow_redirects=True)
with app.app_context():
    it_bad = db.session.get(ItemRequest, requested_item_id)
    assert it_bad.status == ItemStatus.REQUESTED  # Remains REQUESTED
print("[OK] Verified: Only SHIPPED items can be marked as RECEIVED")


print("\n>>> ALL MILESTONE 4 CHECKS PASSED SUCCESSFULLY! <<<")
