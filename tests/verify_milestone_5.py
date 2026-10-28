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

print("Starting Milestone 5 Verification Suite...")


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


# 0. Setup test users and teams
with app.app_context():
    u_uid = uuid.uuid4().hex[:6]
    staff = User(
        username=f'staff_m5_{u_uid}',
        name='Staf Lapangan M5',
        phone_number=f'+62813{uuid.uuid4().int % 100000000:08d}',
        role=RoleEnum.STAFF,
        is_active=True
    )
    staff.set_password('StaffPass123!')
    db.session.add(staff)

    team = Team(
        name=f'Tim Perawatan M5 {u_uid}',
        description='Divisi pemeliharaan dan review Milestone 5',
        is_active=True
    )
    team.members.append(staff)
    db.session.add(team)
    db.session.commit()

    staff_id = staff.id
    staff_user = staff.username
    team_id = team.id

c_admin = login_client('admin', 'AdminPassword123!')
c_staff = login_client(staff_user, 'StaffPass123!')

print("[OK] Test environment and users initialized")


# =========================================================================
# 1. Access Control: Non-admin blocked from /admin/logistics & /admin/review-queue
# =========================================================================
res_log_blocked = c_staff.get('/admin/logistics', follow_redirects=False)
assert res_log_blocked.status_code == 302 and '/tasks/' in res_log_blocked.headers['Location']

res_rev_blocked = c_staff.get('/admin/review-queue', follow_redirects=False)
assert res_rev_blocked.status_code == 302 and '/tasks/' in res_rev_blocked.headers['Location']
print("[OK] Access control verified: Non-admin blocked from logistics and review queue")


# =========================================================================
# 2. Logistics Workflow (Steps 42, 43, 44)
# =========================================================================
# 2a. Create a task with 3 requested items
with app.app_context():
    task = Task(
        title=f'Penggantian Pompa Booster {uuid.uuid4().hex[:6]}',
        description='Penggantian unit pompa booster dan fitting inlet outlet',
        status=TaskStatus.IN_PROGRESS,
        created_by_id=1,
        assigned_user_id=staff_id
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.id
    task_title = task.title

csrf = get_csrf(c_staff, f'/tasks/{task_id}')
c_staff.post(
    f'/tasks/{task_id}/request-items',
    data={
        'item_names[]': ['Pompa Booster 1HP', 'Valve Kuningan 1 inch', 'Sealtape'],
        'quantities[]': ['1 unit', '2 pcs', '5 roll'],
        'notes[]': ['Grundfos CMB', 'Kitazawa', 'Onda'],
        'csrf_token': csrf
    },
    follow_redirects=True
)

with app.app_context():
    items = ItemRequest.query.filter_by(task_id=task_id).all()
    assert len(items) == 3
    for it in items:
        assert it.status == ItemStatus.REQUESTED
    it1_id, it2_id, it3_id = items[0].id, items[1].id, items[2].id

# 2b. Admin views /admin/logistics
res_log = c_admin.get('/admin/logistics')
assert res_log.status_code == 200
html_log = res_log.get_data(as_text=True)
assert task_title in html_log
assert 'Pompa Booster 1HP' in html_log
assert 'Pesan Semua Barang' in html_log
print("[OK] Verified: Logistics dashboard renders grouped tasks and items")

# 2c. Admin advances single item it1 to ORDERED
csrf = get_csrf(c_admin, '/admin/logistics')
res_ord1 = c_admin.post(f'/admin/logistics/{it1_id}/order', data={'csrf_token': csrf}, follow_redirects=True)
assert res_ord1.status_code == 200

with app.app_context():
    it1 = db.session.get(ItemRequest, it1_id)
    assert it1.status == ItemStatus.ORDERED
    assert it1.ordered_at is not None

    # Requester notified
    notif = Notification.query.filter_by(user_id=staff_id).order_by(Notification.created_at.desc()).first()
    assert notif is not None
    assert 'Dipesan' in notif.title
    print("[OK] Verified: Single item advanced to ORDERED with timestamp and requester notification")

# 2d. Admin uses batch order-all for remaining requested items (it2 & it3)
csrf = get_csrf(c_admin, '/admin/logistics')
res_batch_ord = c_admin.post(f'/admin/logistics/tasks/{task_id}/order-all', data={'csrf_token': csrf}, follow_redirects=True)
assert res_batch_ord.status_code == 200

with app.app_context():
    it2 = db.session.get(ItemRequest, it2_id)
    it3 = db.session.get(ItemRequest, it3_id)
    assert it2.status == ItemStatus.ORDERED and it2.ordered_at is not None
    assert it3.status == ItemStatus.ORDERED and it3.ordered_at is not None
    print("[OK] Verified: Batch order-all advanced all requested items to ORDERED")

# 2e. Admin advances single item it1 to SHIPPED
csrf = get_csrf(c_admin, '/admin/logistics')
res_ship1 = c_admin.post(f'/admin/logistics/{it1_id}/ship', data={'csrf_token': csrf}, follow_redirects=True)
assert res_ship1.status_code == 200

with app.app_context():
    it1 = db.session.get(ItemRequest, it1_id)
    assert it1.status == ItemStatus.SHIPPED
    assert it1.shipped_at is not None

    notif = Notification.query.filter_by(user_id=staff_id).order_by(Notification.created_at.desc()).first()
    assert 'Dikirim' in notif.title
    print("[OK] Verified: Single item advanced to SHIPPED with timestamp and requester notification")

# 2f. Admin uses batch ship-all for remaining ordered items (it2 & it3)
csrf = get_csrf(c_admin, '/admin/logistics')
res_batch_ship = c_admin.post(f'/admin/logistics/tasks/{task_id}/ship-all', data={'csrf_token': csrf}, follow_redirects=True)
assert res_batch_ship.status_code == 200

with app.app_context():
    it2 = db.session.get(ItemRequest, it2_id)
    it3 = db.session.get(ItemRequest, it3_id)
    assert it2.status == ItemStatus.SHIPPED and it2.shipped_at is not None
    assert it3.status == ItemStatus.SHIPPED and it3.shipped_at is not None
    print("[OK] Verified: Batch ship-all advanced all ordered items to SHIPPED")

# 2g. Staff receives item it1
csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_rcv = c_staff.post(f'/tasks/{task_id}/items/{it1_id}/receive', data={'csrf_token': csrf}, follow_redirects=True)
assert res_rcv.status_code == 200

with app.app_context():
    it1 = db.session.get(ItemRequest, it1_id)
    assert it1.status == ItemStatus.RECEIVED
    assert it1.received_at is not None
    print("[OK] Verified: Staff marked item as RECEIVED (full logistics lifecycle verified)")


# =========================================================================
# 3. Submit Task for Review (Step 45)
# =========================================================================
# Add a subtask (1 completed, 1 uncompleted) to verify flexible review submission
with app.app_context():
    st1 = SubTask(task_id=task_id, title='Bongkar pompa lama', is_completed=True, created_by_id=staff_id)
    st2 = SubTask(task_id=task_id, title='Pasang fitting inlet outlet', is_completed=False, created_by_id=staff_id)
    db.session.add_all([st1, st2])
    db.session.commit()

csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_subm = c_staff.post(f'/tasks/{task_id}/submit-review', data={'csrf_token': csrf}, follow_redirects=True)
assert res_subm.status_code == 200

with app.app_context():
    t = db.session.get(Task, task_id)
    assert t.status == TaskStatus.WAITING_REVIEW
    assert t.pending_reason is None

    # Admins received notification
    admin_user = User.query.filter_by(username='admin').first()
    notif = Notification.query.filter_by(user_id=admin_user.id).order_by(Notification.created_at.desc()).first()
    assert notif is not None
    assert 'Review Diajukan' in notif.title
    print("[OK] Verified: Staff submitted task for review (WAITING_REVIEW) and admins notified")

# Task detail shows WAITING_REVIEW banner
res_detail = c_staff.get(f'/tasks/{task_id}')
assert 'Menunggu Evaluasi Administrator' in res_detail.get_data(as_text=True)


# =========================================================================
# 4. Review Queue & Request Continuation (Steps 46, 47, 48)
# =========================================================================
# Admin opens /admin/review-queue
res_q = c_admin.get('/admin/review-queue')
assert res_q.status_code == 200
html_q = res_q.get_data(as_text=True)
assert task_title in html_q
assert 'Bongkar pompa lama' in html_q
assert 'Pasang fitting inlet outlet' in html_q
# Visual warning about unreceived materials (it2 and it3 are SHIPPED, not RECEIVED)
assert 'belum berstatus Diterima' in html_q
print("[OK] Verified: Review Queue renders task with subtask checklist and material warning banner")

# 4b. Admin requests continuation with review notes
review_note_text = "Fitting inlet masih agak longgar, tolong rekatkan sealtape ekstra dan kencangkan baut flange."
csrf = get_csrf(c_admin, '/admin/review-queue')
res_cont = c_admin.post(
    f'/admin/review-queue/{task_id}/request-continuation',
    data={'review_notes': review_note_text, 'csrf_token': csrf},
    follow_redirects=True
)
assert res_cont.status_code == 200

with app.app_context():
    t = db.session.get(Task, task_id)
    assert t.status == TaskStatus.IN_PROGRESS
    assert t.review_notes == review_note_text

    # Staff received notification
    notif = Notification.query.filter_by(user_id=staff_id).order_by(Notification.created_at.desc()).first()
    assert notif is not None
    assert 'Perbaikan Tugas' in notif.title
    assert review_note_text in notif.message
    print("[OK] Verified: Request continuation returned task to IN_PROGRESS, saved review_notes, and notified staff")

# 4c. Verify purple banner appears on staff task detail
res_detail_notes = c_staff.get(f'/tasks/{task_id}')
html_notes = res_detail_notes.get_data(as_text=True)
assert 'Catatan Evaluasi / Permintaan Perbaikan' in html_notes
assert review_note_text in html_notes
print("[OK] Verified: Purple evaluation notes banner displayed on task detail")


# =========================================================================
# 5. Re-Submit & Approval Flow (Step 48)
# =========================================================================
# 5a. Staff marks remaining subtask completed and re-submits review
with app.app_context():
    st2 = SubTask.query.filter_by(task_id=task_id, title='Pasang fitting inlet outlet').first()
    st2.is_completed = True
    db.session.commit()

csrf = get_csrf(c_staff, f'/tasks/{task_id}')
res_resub = c_staff.post(f'/tasks/{task_id}/submit-review', data={'csrf_token': csrf}, follow_redirects=True)
assert res_resub.status_code == 200

with app.app_context():
    t = db.session.get(Task, task_id)
    assert t.status == TaskStatus.WAITING_REVIEW
    # review_notes is cleaned upon re-submission per grill-me decision
    assert t.review_notes is None
    print("[OK] Verified: Re-submitting review cleared review_notes and set status back to WAITING_REVIEW")

# 5b. Admin approves the task
csrf = get_csrf(c_admin, '/admin/review-queue')
res_appr = c_admin.post(f'/admin/review-queue/{task_id}/approve', data={'csrf_token': csrf}, follow_redirects=True)
assert res_appr.status_code == 200

with app.app_context():
    t = db.session.get(Task, task_id)
    assert t.status == TaskStatus.COMPLETED

    # Staff notified of approval
    notif = Notification.query.filter_by(user_id=staff_id).order_by(Notification.created_at.desc()).first()
    assert notif is not None
    assert 'Disetujui' in notif.title
    print("[OK] Verified: Admin approved task, status set to COMPLETED, and staff notified")

# 5c. Task detail shows completed green banner
res_detail_done = c_staff.get(f'/tasks/{task_id}')
assert 'Tugas Telah Selesai' in res_detail_done.get_data(as_text=True)
print("[OK] Verified: Completed green banner displayed on task detail")


print("\n>>> ALL MILESTONE 5 CHECKS PASSED SUCCESSFULLY! <<<")

