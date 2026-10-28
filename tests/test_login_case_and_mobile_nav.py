"""
Test Suite: Case-Insensitive Login & Mobile Navigation Verification
Verifies:
1. Case-insensitive login for username (e.g. 'ADMIN', 'Admin', 'admin', 'Ryan', 'RYAN').
2. Case-insensitive login for email (e.g. 'ADMIN@EXAMPLE.COM', 'Admin@example.com').
3. Mobile Admin View:
   - Bottom bar contains 'Tim' (/admin/teams), 'Pengguna' (/admin/users), 'Tugas', 'Pesan', 'Profil' (5 columns).
   - Mobile slide-over drawer contains full admin links (Logistik, Review Queue, Pengguna, Tim).
4. Mobile Staff View:
   - Bottom bar contains exactly 'Tugas', 'Pesan', 'Profil' (3 columns).
   - 'Aktivitas' duplicate menu is completely removed.
"""
import os
import sys
import re
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import User, RoleEnum

app = create_app()


def get_csrf(client, url):
    res = client.get(url)
    match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', res.get_data(as_text=True))
    assert match, f"CSRF token not found in {url}"
    return match.group(1)


print("\n" + "=" * 70)
print("  TaskOps: Case-Insensitive Login & Mobile Navigation Verification  ")
print("=" * 70)

# =========================================================================
# 1. Case-Insensitive Login Verification
# =========================================================================
print("\n--- [1/3] Login Case-Insensitivity (Username & Email) ---")
unique_id = uuid.uuid4().hex[:6]
test_username = f"ryan_{unique_id}"
test_email = f"ryan_{unique_id}@example.com"
test_password = "PasswordRyan123!"

with app.app_context():
    admin_user = User.query.filter_by(username='admin').first()
    if admin_user:
        admin_user.set_password('AdminPassword123!')
        db.session.commit()

    user = User(
        username=test_username,
        name=f"Ryan Tester {unique_id}",
        email=test_email,
        phone_number=f"+62899{unique_id[:8]}",
        role=RoleEnum.STAFF,
        is_active=True
    )
    user.set_password(test_password)
    db.session.add(user)
    db.session.commit()

# Test 1A: Login dengan LOWERCASE username
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    res = client.post('/auth/login', data={'identifier': test_username.lower(), 'password': test_password, 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200
    assert 'Dasbor Tugas' in res.get_data(as_text=True)
    print(f"  [OK] Login lowercase: '{test_username.lower()}' berhasil")

# Test 1B: Login dengan UPPERCASE username
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    res = client.post('/auth/login', data={'identifier': test_username.upper(), 'password': test_password, 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200
    assert 'Dasbor Tugas' in res.get_data(as_text=True)
    print(f"  [OK] Login uppercase: '{test_username.upper()}' berhasil")

# Test 1C: Login dengan TITLE CASE username (misal: 'Ryan_...')
title_username = test_username.capitalize()
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    res = client.post('/auth/login', data={'identifier': title_username, 'password': test_password, 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200
    assert 'Dasbor Tugas' in res.get_data(as_text=True)
    print(f"  [OK] Login title-case: '{title_username}' berhasil")

# Test 1D: Login Admin dengan 'ADMIN' uppercase
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    res = client.post('/auth/login', data={'identifier': 'ADMIN', 'password': 'AdminPassword123!', 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200
    assert 'Dasbor Tugas' in res.get_data(as_text=True)
    print("  [OK] Login admin uppercase: 'ADMIN' berhasil")

# Test 1E: Login dengan UPPERCASE email
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    res = client.post('/auth/login', data={'identifier': test_email.upper(), 'password': test_password, 'csrf_token': csrf}, follow_redirects=True)
    assert res.status_code == 200
    assert 'Dasbor Tugas' in res.get_data(as_text=True)
    print(f"  [OK] Login email uppercase: '{test_email.upper()}' berhasil")

print("[OK] Verifikasi login case-insensitive untuk username dan email tuntas 100%")


# =========================================================================
# 2. Verifikasi Mobile Admin View (Manage Team & 5 Kolom Bottom Bar)
# =========================================================================
print("\n--- [2/3] Mobile Admin Navigation View ---")
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    client.post('/auth/login', data={'identifier': 'admin', 'password': 'AdminPassword123!', 'csrf_token': csrf}, follow_redirects=True)
    
    res = client.get('/tasks/')
    html = res.get_data(as_text=True)

    # 1. Pastikan bottom bar Admin memiliki 5 kolom
    assert 'grid-cols-5' in html, "Mobile Admin bottom bar must have 5 columns"
    # 2. Pastikan ada tautan Tim di bottom bar
    assert '/admin/teams' in html, "Admin view must contain link to /admin/teams"
    assert '>Tim</span>' in html, "Bottom bar must render 'Tim' label for Admin"
    # 3. Pastikan ada tautan Pengguna di bottom bar
    assert '/admin/users' in html, "Admin view must contain link to /admin/users"
    assert '>Pengguna</span>' in html, "Bottom bar must render 'Pengguna' label for Admin"
    # 4. Pastikan hamburger menu button dan mobile drawer ada
    assert 'toggleMobileDrawer()' in html, "Header must render toggleMobileDrawer() button"
    assert 'id="mobile-drawer"' in html, "Mobile drawer panel must exist in DOM"
    assert '/admin/logistics' in html, "Mobile drawer must include logistics"
    assert '/admin/review-queue' in html, "Mobile drawer must include review queue"

print("[OK] Mobile Admin View memiliki menu 'Tim' (/admin/teams), 'Pengguna' (/admin/users), dan drawer administrasi lengkap")


# =========================================================================
# 3. Verifikasi Mobile Staff View (Hapus Duplikat 'Aktivitas')
# =========================================================================
print("\n--- [3/3] Mobile Staff Navigation View ---")
with app.test_client() as client:
    csrf = get_csrf(client, '/auth/login')
    client.post('/auth/login', data={'identifier': test_username, 'password': test_password, 'csrf_token': csrf}, follow_redirects=True)
    
    res = client.get('/tasks/')
    html = res.get_data(as_text=True)

    # 1. Pastikan bottom bar Staff memiliki 3 kolom (Tugas, Pesan, Profil)
    assert 'grid-cols-3' in html, "Mobile Staff bottom bar must have 3 columns"
    # 2. Pastikan 'Aktivitas' TIDAK ada di bottom bar
    assert '>Aktivitas</span>' not in html, "'Aktivitas' duplicate menu must be removed from Staff view"
    # 3. Pastikan tautan Tugas, Pesan, Profil ada
    assert '>Tugas</span>' in html
    assert '>Pesan</span>' in html
    assert '>Profil</span>' in html
    # 4. Pastikan Staff tidak melihat tautan admin
    assert '/admin/teams' not in html
    assert '/admin/users' not in html

print("[OK] Mobile Staff View bersih: 3 kolom (Tugas, Pesan, Profil), duplikat 'Aktivitas' berhasil dihilangkan")

print("\n" + "=" * 70)
print("  >>> SELURUH PERBAIKAN LOGIN & NAVIGASI MOBILE LULUS 100%! <<<       ")
print("=" * 70 + "\n")

