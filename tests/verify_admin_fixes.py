import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import User, Team, Task, TaskStatus, RoleEnum
from app.extensions import db

print("Starting Admin Fixes Verification...")

def get_csrf(client, url):
    res = client.get(url)
    match = re.search(r'name="csrf_token" value="([^"]+)"', res.get_data(as_text=True))
    assert match is not None, f"CSRF token not found on {url}"
    return match.group(1)

def login_as_admin():
    c = app.test_client()
    csrf = get_csrf(c, '/auth/login')
    # Try INITIAL_ADMIN_PASSWORD from env, fallback to 'admin' or 'AdminPassword123!'
    pw = os.environ.get('INITIAL_ADMIN_PASSWORD', 'admin')
    res = c.post('/auth/login', data={'identifier': 'admin', 'password': pw, 'csrf_token': csrf}, follow_redirects=True)
    if 'Dasbor Tugas' not in res.get_data(as_text=True):
        c.post('/auth/login', data={'identifier': 'admin', 'password': 'AdminPassword123!', 'csrf_token': csrf}, follow_redirects=True)
    return c

c_admin = login_as_admin()

# 1. Verify that inactive users are not attached to any teams in DB
with app.app_context():
    inactive_users = User.query.filter_by(is_active=False).all()
    for u in inactive_users:
        assert len(u.teams) == 0, f"Inactive user @{u.username} should have 0 teams"
    print("[OK] Verified: All inactive users have 0 team memberships in database")

# 2. Test AJAX validation on user creation (Anti-Reset error handling)
csrf = get_csrf(c_admin, '/admin/users')
res = c_admin.post(
    '/admin/users',
    data={
        'username': 'short_pass_user',
        'name': 'Short Pass',
        'phone_number': '+6281234567898',
        'password': '123', # Less than 6 characters
        'role': RoleEnum.STAFF.value,
        'csrf_token': csrf
    },
    headers={'X-Requested-With': 'XMLHttpRequest'}
)
assert res.status_code == 400, f"Expected 400 for short password, got {res.status_code}"
json_data = res.get_json()
assert json_data['status'] == 'error'
assert 'Kata sandi minimal 6 karakter' in json_data['message']
print("[OK] Verified: AJAX user creation returns error JSON with status 400 and does not crash")

# 3. Test Pure Team Creation (Without members)
import uuid
unique_team_name = f'Tim Pengawasan {uuid.uuid4().hex[:6]}'
csrf = get_csrf(c_admin, '/admin/teams')
res = c_admin.post(
    '/admin/teams',
    data={
        'name': unique_team_name,
        'description': 'Divisi pengawasan mutu dan safety',
        'csrf_token': csrf
    },
    headers={'X-Requested-With': 'XMLHttpRequest'}
)
assert res.status_code == 200 or res.status_code == 302
with app.app_context():
    team = Team.query.filter_by(name=unique_team_name).first()
    assert team is not None, "Team was not created"
    assert len(team.members) == 0, "Team should be created with 0 members"
    team_id = team.id
print("[OK] Verified: Pure team creation succeeds with only name and description (0 members)")

# 4. Test Team Members Data API & Assignment (Chips)
res_data = c_admin.get(f'/admin/teams/{team_id}/members-data')
assert res_data.status_code == 200
data_json = res_data.get_json()
assert data_json['status'] == 'success'
assert len(data_json['current_members']) == 0
assert any(u['username'] == 'admin' for u in data_json['available_users'])
print("[OK] Verified: /members-data returns available active users and empty current members")

# Assign admin to team
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    admin_id = admin.id

csrf = get_csrf(c_admin, '/admin/teams')
res_assign = c_admin.post(
    f'/admin/teams/{team_id}/members',
    data={'member_ids': [str(admin_id)], 'csrf_token': csrf},
    headers={'X-Requested-With': 'XMLHttpRequest'}
)
assert res_assign.status_code in (200, 302)
with app.app_context():
    team = db.session.get(Team, team_id)
    assert len(team.active_members) == 1
    assert team.active_members[0].username == 'admin'
print("[OK] Verified: Team member assignment via chip endpoint succeeded")

# 5. Test that user deletion immediately detaches user from team
# Create a temporary user
with app.app_context():
    temp_user = User(
        username=f'temp_{uuid.uuid4().hex[:6]}',
        name='Temp Team User',
        phone_number='+6281234567888',
        role=RoleEnum.STAFF,
        is_active=True
    )
    temp_user.set_password('TempPass123!')
    team = db.session.get(Team, team_id)
    team.members.append(temp_user)
    db.session.add(temp_user)
    db.session.commit()
    temp_id = temp_user.id

with app.app_context():
    team = db.session.get(Team, team_id)
    assert any(m.id == temp_id for m in team.active_members)

# Delete temp_user
csrf = get_csrf(c_admin, '/admin/users')
res_del = c_admin.post(f'/admin/users/{temp_id}/delete', data={'csrf_token': csrf}, follow_redirects=True)
assert res_del.status_code == 200

# Verify temp_user is detached from team
with app.app_context():
    team = db.session.get(Team, team_id)
    assert not any(m.id == temp_id for m in team.members), "Deleted user must be detached from team.members"
    assert not any(m.id == temp_id for m in team.active_members), "Deleted user must not be in active_members"
print("[OK] Verified: Deleting/deactivating a user immediately detaches them from all teams")

# 6. Check UI rendering of /admin/teams
res_ui = c_admin.get('/admin/teams')
assert res_ui.status_code == 200
html = res_ui.get_data(as_text=True)
assert 'Kelola Anggota' in html
assert 'Edit Info' in html
assert 'Hapus' in html
# Temp Team User was deleted and detached, so it must not be rendered on active team cards
assert 'Temp Team User' not in html
print("[OK] Verified: /admin/teams UI renders 'Kelola Anggota' and no inactive users appear on active cards")

# 7. Test that deactivating/deleting a team immediately severs members & does not appear on /admin/users
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    test_deact_team = Team(
        name=f'Tim Tes Hapus {uuid.uuid4().hex[:6]}',
        description='Tim untuk tes pemutusan anggota saat dihapus',
        is_active=True
    )
    test_deact_team.members.append(admin)
    db.session.add(test_deact_team)
    db.session.commit()
    deact_team_id = test_deact_team.id
    deact_team_name = test_deact_team.name

    # Create dummy task tie to trigger soft-deactivation (archive)
    dummy_task = Task(
        title='Dummy Task for Team History',
        created_by_id=admin.id,
        assigned_team_id=deact_team_id
    )
    db.session.add(dummy_task)
    db.session.commit()

# Verify team is visible on /admin/users initially
res_users = c_admin.get('/admin/users')
assert deact_team_name in res_users.get_data(as_text=True)

# Delete (deactivate) the team
csrf = get_csrf(c_admin, '/admin/teams')
res_del_team = c_admin.post(f'/admin/teams/{deact_team_id}/delete', data={'csrf_token': csrf}, follow_redirects=True)
assert res_del_team.status_code == 200

# Verify in DB: members are severed and active_teams does not include the team
with app.app_context():
    team = db.session.get(Team, deact_team_id)
    assert team.is_active is False
    assert len(team.members) == 0, "Deactivated team must have members cleared"
    admin = User.query.filter_by(username='admin').first()
    assert deact_team_name not in [t.name for t in admin.active_teams]

# Verify in UI: /admin/users no longer displays the deactivated team
res_users_after = c_admin.get('/admin/users')
assert deact_team_name not in res_users_after.get_data(as_text=True), "Deactivated team badge must not appear in /admin/users"
print("[OK] Verified: Deactivating/deleting a team severs members and disappears from /admin/users")

print("\n>>> ALL ADMIN FIXES VERIFIED SUCCESSFULLY! <<<")
