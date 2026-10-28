import os
import sys
import re
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import User, Team, Task, TaskStatus, RoleEnum, validate_username, validate_e164_phone
from app.extensions import db

print("Starting Milestone 3 Comprehensive Verification...")

# 1. Helper function tests
assert validate_username('budi_ops') is True
assert validate_username('ab') is False
assert validate_username('user@invalid') is False
assert validate_username('user.name_123') is True
assert validate_e164_phone('+6281234567890') is True
assert validate_e164_phone('081234567890') is False
print("[OK] Username and Phone validation helper tests passed")

def get_csrf(client, url):
    res = client.get(url)
    match = re.search(r'name="csrf_token" value="([^"]+)"', res.get_data(as_text=True))
    assert match is not None, f"CSRF token not found on {url}"
    return match.group(1)

def login_as_admin():
    c = app.test_client()
    csrf = get_csrf(c, '/auth/login')
    c.post('/auth/login', data={'identifier': 'admin', 'password': 'AdminPassword123!', 'csrf_token': csrf})
    return c

# 2. Access control: Non-admin redirection test
with app.app_context():
    staff_user = User.query.filter_by(username='test_staff_guard').first()
    if not staff_user:
        staff_user = User(
            username='test_staff_guard',
            name='Staff Guard',
            role=RoleEnum.STAFF,
            is_active=True
        )
        staff_user.set_password('StaffPassword123!')
        db.session.add(staff_user)
        db.session.commit()

c_staff = app.test_client()
csrf = get_csrf(c_staff, '/auth/login')
c_staff.post('/auth/login', data={'identifier': 'test_staff_guard', 'password': 'StaffPassword123!', 'csrf_token': csrf})

res = c_staff.get('/admin/users', follow_redirects=False)
assert res.status_code == 302 and '/tasks/' in res.headers['Location']
res = c_staff.get('/admin/teams', follow_redirects=False)
assert res.status_code == 302 and '/tasks/' in res.headers['Location']
print("[OK] Access control verified: Non-admin users are blocked from admin routes")

# 3. User CRUD tests
c_admin = login_as_admin()
ts = str(int(time.time()))[-4:]
u_staff = f"staff_{ts}"
u_admin2 = f"admin_{ts}"

# 3a. Create staff user
csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post('/admin/users', data={
    'username': u_staff,
    'name': 'Budi Setiawan',
    'phone_number': f'+6281234{ts}',
    'email': f'staff_{ts}@example.com',
    'password': 'BudiPassword123!',
    'role': RoleEnum.STAFF.value,
    'csrf_token': csrf
}, follow_redirects=True)
assert u_staff in res.get_data(as_text=True)

# 3b. Create second admin user
csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post('/admin/users', data={
    'username': u_admin2,
    'name': 'Siti Rahma',
    'phone_number': f'+6281235{ts}',
    'email': f'admin_{ts}@example.com',
    'password': 'SitiPassword123!',
    'role': RoleEnum.ADMIN.value,
    'csrf_token': csrf
}, follow_redirects=True)
assert u_admin2 in res.get_data(as_text=True)
print("[OK] User creation verified for Staff and Admin")

# 3c. Edit user profile
with app.app_context():
    budi = User.query.filter_by(username=u_staff).first()
    assert budi is not None
    budi_id = budi.id

csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post(f'/admin/users/{budi_id}/edit', data={
    'username': u_staff,
    'name': 'Budi Santoso',
    'phone_number': f'+6281236{ts}',
    'email': f'budi_{ts}_new@example.com',
    'role': RoleEnum.STAFF.value,
    'csrf_token': csrf
}, follow_redirects=True)
assert 'Budi Santoso' in res.get_data(as_text=True)
print("[OK] User profile edit verified")

# 3d. Dedicated Reset Password modal & verification
csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post(f'/admin/users/{budi_id}/reset-password', data={
    'new_password': 'NewBudiPassword123!',
    'confirm_password': 'NewBudiPassword123!',
    'csrf_token': csrf
}, follow_redirects=True)

# Verify Budi can log in with new password
c_budi = app.test_client()
csrf_budi = get_csrf(c_budi, '/auth/login')
res_login = c_budi.post('/auth/login', data={
    'identifier': u_staff,
    'password': 'NewBudiPassword123!',
    'csrf_token': csrf_budi
}, follow_redirects=False)
assert res_login.status_code == 302 and '/tasks/' in res_login.headers['Location']
print("[OK] Dedicated password reset verified and authenticated successfully")

# 4. Smart Deletion for Users
# 4a. User WITHOUT history (u_admin2): must be PERMANENTLY deleted
with app.app_context():
    siti = User.query.filter_by(username=u_admin2).first()
    siti_id = siti.id

csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post(f'/admin/users/{siti_id}/delete', data={'csrf_token': csrf}, follow_redirects=True)
assert 'berhasil dihapus secara permanen' in res.get_data(as_text=True)
with app.app_context():
    assert User.query.filter_by(username=u_admin2).first() is None
print("[OK] Smart deletion (permanent delete) verified for user without historical ties")

# 4b. User WITH history (u_staff): must be DEACTIVATED (is_active = False)
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    admin_id = admin.id
    budi = User.query.filter_by(username=u_staff).first()
    task_hist = Task(
        title=f"Perbaikan Pipa {ts}",
        description="Pipa bocor di lantai 2",
        status=TaskStatus.TODO,
        created_by_id=budi.id,
        assigned_user_id=budi.id
    )
    db.session.add(task_hist)
    db.session.commit()

csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post(f'/admin/users/{budi_id}/delete', data={'csrf_token': csrf}, follow_redirects=True)
assert 'dinonaktifkan (diarsipkan)' in res.get_data(as_text=True)
with app.app_context():
    budi_check = User.query.filter_by(username=u_staff).first()
    assert budi_check is not None, "User with history should not be physically deleted"
    assert budi_check.is_active is False, "User should be marked inactive"
print("[OK] Smart deletion (auto-deactivate archive) verified for user with historical ties")

# 4c. Reactivate user
csrf = get_csrf(c_admin, '/admin/users?tab=inactive')
res = c_admin.post(f'/admin/users/{budi_id}/reactivate', data={'csrf_token': csrf}, follow_redirects=True)
assert 'berhasil diaktifkan kembali' in res.get_data(as_text=True)
with app.app_context():
    budi_check = User.query.filter_by(username=u_staff).first()
    assert budi_check.is_active is True
print("[OK] User reactivation verified")

# 5. Team Creation & Separate Member Assignment (Chip Workflow)
# 5a. Create Team 1 (Pure creation)
team1_name = f"Tim Mekanikal {ts}"
csrf = get_csrf(c_admin, '/admin/teams')
res = c_admin.post('/admin/teams', data={
    'name': team1_name,
    'description': 'Pemeliharaan HVAC dan Plumbing',
    'csrf_token': csrf
}, follow_redirects=True)
assert team1_name in res.get_data(as_text=True)

with app.app_context():
    t1 = Team.query.filter_by(name=team1_name).first()
    t1_id = t1.id

# 5b. Assign budi & admin to Team 1
csrf = get_csrf(c_admin, '/admin/teams')
res = c_admin.post(f'/admin/teams/{t1_id}/members', data={
    'member_ids': [str(budi_id), str(admin_id)],
    'csrf_token': csrf
}, follow_redirects=True)
assert res.status_code == 200

# 5c. Create Team 2 and assign budi
team2_name = f"Tim Listrik {ts}"
csrf = get_csrf(c_admin, '/admin/teams')
c_admin.post('/admin/teams', data={
    'name': team2_name,
    'description': 'Instalasi panel dan genset',
    'csrf_token': csrf
}, follow_redirects=True)

with app.app_context():
    t2 = Team.query.filter_by(name=team2_name).first()
    t2_id = t2.id

csrf = get_csrf(c_admin, '/admin/teams')
c_admin.post(f'/admin/teams/{t2_id}/members', data={
    'member_ids': [str(budi_id)],
    'csrf_token': csrf
}, follow_redirects=True)

with app.app_context():
    budi = User.query.filter_by(username=u_staff).first()
    team_names = [t.name for t in budi.teams]
    assert team1_name in team_names and team2_name in team_names
print("[OK] Many-to-Many team membership verified via separate assignment")

# 5d. Empty team (0 members allowed)
team3_name = f"Tim Cadangan {ts}"
csrf = get_csrf(c_admin, '/admin/teams')
res = c_admin.post('/admin/teams', data={
    'name': team3_name,
    'description': 'Tim standby tanpa anggota',
    'csrf_token': csrf
}, follow_redirects=True)
assert team3_name in res.get_data(as_text=True)
with app.app_context():
    t_cad = Team.query.filter_by(name=team3_name).first()
    assert t_cad is not None and len(t_cad.members) == 0
print("[OK] Empty team (0 members) created successfully")

# 6. Smart Deletion for Teams
# 6a. Team WITHOUT history: permanently deleted
with app.app_context():
    t_cad_id = Team.query.filter_by(name=team3_name).first().id

csrf = get_csrf(c_admin, '/admin/teams')
res = c_admin.post(f'/admin/teams/{t_cad_id}/delete', data={'csrf_token': csrf}, follow_redirects=True)
assert 'berhasil dihapus secara permanen' in res.get_data(as_text=True)
with app.app_context():
    assert Team.query.filter_by(name=team3_name).first() is None
print("[OK] Smart deletion (permanent delete) verified for team without historical ties")

# 6b. Team WITH history: assign a task to team, then delete
with app.app_context():
    task_team = Task(
        title=f"Pembersihan Saluran {ts}",
        status=TaskStatus.TODO,
        created_by_id=admin_id,
        assigned_team_id=t1_id
    )
    db.session.add(task_team)
    db.session.commit()

csrf = get_csrf(c_admin, '/admin/teams')
res = c_admin.post(f'/admin/teams/{t1_id}/delete', data={'csrf_token': csrf}, follow_redirects=True)
assert 'dinonaktifkan (diarsipkan)' in res.get_data(as_text=True)
with app.app_context():
    t1_check = Team.query.filter_by(name=team1_name).first()
    assert t1_check is not None, "Team with history should not be physically deleted"
    assert t1_check.is_active is False
print("[OK] Smart deletion (auto-deactivate archive) verified for team with historical ties")

# 6c. Reactivate team
csrf = get_csrf(c_admin, '/admin/teams?tab=inactive')
res = c_admin.post(f'/admin/teams/{t1_id}/reactivate', data={'csrf_token': csrf}, follow_redirects=True)
assert 'berhasil diaktifkan kembali' in res.get_data(as_text=True)
with app.app_context():
    t1_check = Team.query.filter_by(name=team1_name).first()
    assert t1_check.is_active is True
print("[OK] Team reactivation verified")

# 7. Indonesian UI & Templates verification
res_users_ui = c_admin.get('/admin/users')
assert res_users_ui.status_code == 200
content_u = res_users_ui.get_data(as_text=True)
assert 'Manajemen Pengguna' in content_u
assert 'Tambah Pengguna Baru' in content_u
assert 'Keanggotaan Tim (Read-Only)' in content_u

res_teams_ui = c_admin.get('/admin/teams')
assert res_teams_ui.status_code == 200
content_t = res_teams_ui.get_data(as_text=True)
assert 'Manajemen Tim' in content_t
assert 'Buat Tim Baru' in content_t
assert 'Kelola Anggota' in content_t
print("[OK] Indonesian UI elements and read-only team badges verified")

print("\n>>> ALL MILESTONE 3 CHECKS PASSED SUCCESSFULLY! <<<")
