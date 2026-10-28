import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from app.models import User, PushSubscription, validate_e164_phone
from app.extensions import db

print("Starting Milestone 2 Verification...")

# 1. Phone validation
assert validate_e164_phone('+6281234567890') is True
assert validate_e164_phone('081234567890') is False
assert validate_e164_phone(None) is True
print("[OK] Phone validation tests passed")

client = app.test_client()

# 2. Verify admin created
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    assert admin is not None, "Admin not found by username"
    assert admin.phone_number == '+6281234567890', "Phone mismatch"
    assert admin.email == 'admin@example.com', "Email mismatch"
    assert admin.is_admin is True, "Admin role mismatch"
    print("[OK] Admin user verified with username, email, and phone_number")

# 3. Unauthenticated redirect
res = client.get('/')
assert res.status_code == 302 and '/auth/login' in res.headers['Location']
print("[OK] Root unauthenticated redirect verified")

# 4. Login page rendering & PWA meta tags
res = client.get('/auth/login')
assert res.status_code == 200
html = res.get_data(as_text=True)
assert 'manifest.json' in html, "manifest.json link missing"
assert 'theme-color' in html, "theme-color missing"
match = re.search(r'name="csrf_token" value="([^"]+)"', html)
assert match is not None, "CSRF token missing in login form"
csrf_token = match.group(1)
print("[OK] Login page rendering & CSRF token extraction verified")

# 5. Test login via USERNAME
c1 = app.test_client()
res = c1.get('/auth/login')
csrf_token1 = re.search(r'name="csrf_token" value="([^"]+)"', res.get_data(as_text=True)).group(1)
res = c1.post(
    '/auth/login',
    data={'identifier': 'admin', 'password': 'AdminPassword123!', 'csrf_token': csrf_token1},
    follow_redirects=False
)
assert res.status_code == 302 and '/tasks/' in res.headers['Location'], f"Login via username failed: {res.status_code}"
print("[OK] Login via username succeeded (redirects to /tasks/)")

# 6. Test login via PHONE NUMBER
c2 = app.test_client()
res = c2.get('/auth/login')
csrf_token2 = re.search(r'name="csrf_token" value="([^"]+)"', res.get_data(as_text=True)).group(1)
res2 = c2.post(
    '/auth/login',
    data={'identifier': '+6281234567890', 'password': 'AdminPassword123!', 'csrf_token': csrf_token2},
    follow_redirects=False
)
assert res2.status_code == 302 and '/tasks/' in res2.headers['Location'], "Login via phone failed"
print("[OK] Login via phone number succeeded (redirects to /tasks/)")

# 7. Test login via EMAIL
c3 = app.test_client()
res = c3.get('/auth/login')
csrf_token3 = re.search(r'name="csrf_token" value="([^"]+)"', res.get_data(as_text=True)).group(1)
res3 = c3.post(
    '/auth/login',
    data={'identifier': 'admin@example.com', 'password': 'AdminPassword123!', 'csrf_token': csrf_token3},
    follow_redirects=False
)
assert res3.status_code == 302 and '/tasks/' in res3.headers['Location'], "Login via email failed"
print("[OK] Login via email succeeded (redirects to /tasks/)")

# 8. Test Push subscription endpoint with CSRF header
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id)
        sess['_fresh'] = True

    sub_data = {
        'endpoint': 'https://fcm.googleapis.com/fcm/send/test-token-grill',
        'keys': {
            'p256dh': 'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9Q0A4APeWDT1',
            'auth': 'tBHItJI5svbpez7KI4CCXg'
        }
    }
    res_sub = client.post(
        '/auth/push-subscribe',
        json=sub_data,
        headers={'X-CSRFToken': csrf_token, 'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res_sub.status_code == 200, f"Push subscribe failed: {res_sub.status_code}"
    sub = PushSubscription.query.filter_by(user_id=admin.id).first()
    assert sub is not None and sub.endpoint == sub_data['endpoint']
print("[OK] Push subscription registered successfully with CSRF validation")

# 9. Test manifest & sw.js
res_m = client.get('/manifest.json')
assert res_m.status_code == 200 and 'TaskOps' in res_m.get_data(as_text=True)
assert res_m.content_type == 'application/manifest+json'

res_sw = client.get('/sw.js')
assert res_sw.status_code == 200 and res_sw.headers.get('Service-Worker-Allowed') == '/'
assert 'CACHE_NAME' in res_sw.get_data(as_text=True)
print("[OK] Manifest and Service Worker verified")

# 10. Test authenticated dashboard rendering
res_dash = client.get('/tasks/')
assert res_dash.status_code == 200
content = res_dash.get_data(as_text=True)
assert 'Super Admin' in content
assert '@admin' in content
assert '+6281234567890' in content
print("[OK] Authenticated Dashboard rendered successfully with all user fields")

print("\n>>> ALL MILESTONE 2 CHECKS PASSED SUCCESSFULLY! <<<")
