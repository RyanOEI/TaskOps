"""
Test Suite: TaskOps Subtask Summary & Multi-Level File Uploads Verification
Verifies:
1. Subtask summary autosave / edit when unchecked.
2. Checking subtask greys out summary (disabled, readonly, cursor-not-allowed).
3. Attempting to edit summary on completed subtask is blocked (400 Bad Request).
4. Unchecking subtask re-enables summary editing.
5. Task-level file attachment upload (images & documents) with correct storage & metadata.
6. Subtask-level file attachment upload directly linked to subtask with instant OOB swap.
7. Viewing & downloading attachments with secure headers.
8. Collaborative deletion of attachments (DB record & disk file cleanup).
9. SPK print order includes subtask summaries and uploaded attachments table.
"""
import os
import sys
import io
import shutil
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure isolated test environment
test_db_path = os.path.abspath('instance/test_subtask.db')
test_upload_folder = os.path.abspath('instance/test_subtask_uploads')

if os.path.exists(test_db_path):
    try:
        os.remove(test_db_path)
    except Exception:
        pass

if os.path.exists(test_upload_folder):
    shutil.rmtree(test_upload_folder, ignore_errors=True)
os.makedirs(test_upload_folder, exist_ok=True)

os.environ['DATABASE_URL'] = f'sqlite:///{test_db_path}'

from app import create_app
from app.extensions import db
from app.models import (
    User, Team, Task, SubTask, Attachment,
    RoleEnum, TaskStatus, TaskPriority
)

app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{test_db_path}'
app.config['UPLOAD_FOLDER'] = test_upload_folder

print("\n" + "=" * 70)
print("  TaskOps Subtask Summary & File Uploads Comprehensive Verification  ")
print("=" * 70)

with app.app_context():
    db.drop_all()
    db.create_all()

    # Create test users and team
    admin = User(name='Admin TaskOps', username='admin_test', phone_number='+628999999991', role=RoleEnum.ADMIN)
    admin.set_password('AdminPass123!')
    db.session.add(admin)

    tech = User(name='Teknisi Satu', username='tech_test', phone_number='+628999999992', role=RoleEnum.STAFF)
    tech.set_password('TechPass123!')
    db.session.add(tech)
    db.session.flush()

    team = Team(name='Divisi Mekanikal', description='Tim teknisi mesin & mekanikal')
    db.session.add(team)
    db.session.flush()

    team.members.append(tech)

    task = Task(
        title='Overhaul Kompresor Utama Unit 2',
        description='Pembersihan total, ganti oli, dan inspeksi katup kompresor',
        priority=TaskPriority.HIGH,
        status=TaskStatus.IN_PROGRESS,
        assigned_team=team,
        creator=admin
    )
    db.session.add(task)
    db.session.flush()

    subtask = SubTask(
        task=task,
        title='Kuras oli lama dan bersihkan tangki pelumas',
        creator=tech,
        is_completed=False
    )
    db.session.add(subtask)
    db.session.commit()

    task_id = task.id
    subtask_id = subtask.id
    admin_id = admin.id
    tech_id = tech.id

print("[OK] Test database and initial entities initialized.")

client = app.test_client()

def login(user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

# =========================================================================
# 1. Subtask Summary Edit When Unchecked
# =========================================================================
print("\n--- [1/8] Edit Catatan/Ringkasan Subtask Saat Belum Selesai ---")
login(tech_id)

res = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/summary',
    data={'summary': 'Oli lama berwarna keruh, volume 4.5 liter berhasil dikuras.'},
    headers={'HX-Request': 'true'}
)
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
html = res.data.decode('utf-8')
assert 'Oli lama berwarna keruh' in html, "Summary text not rendered in returned subtasks section"

with app.app_context():
    st = db.session.get(SubTask, subtask_id)
    assert st.summary == 'Oli lama berwarna keruh, volume 4.5 liter berhasil dikuras.'
print("[OK] Ringkasan subtask berhasil disimpan dan dirender pada subtasks section.")

# =========================================================================
# 2. Centang Subtask (Toggle Selesai) Menyimpan Ringkasan & Mengunci Field
# =========================================================================
print("\n--- [2/8] Centang Subtask Mengunci (Disabled/Greyed-Out) Field Catatan ---")
res = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/toggle',
    data={'summary': 'Tangki telah dibilas bersih menggunakan solar dan dilap kering.'},
    headers={'HX-Request': 'true'}
)
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
html = res.data.decode('utf-8')

# Pastikan subtask berstatus centang dan textarea greyed out
assert 'line-through text-slate-400' in html, "Subtask title is not struck through"
assert 'disabled' in html, "Textarea must have disabled attribute when completed"
assert 'readonly' in html, "Textarea must have readonly attribute when completed"
assert 'cursor-not-allowed' in html, "Textarea must have cursor-not-allowed class"
assert 'bg-slate-100' in html, "Textarea must have greyed background class"

with app.app_context():
    st = db.session.get(SubTask, subtask_id)
    assert st.is_completed is True
    assert st.summary == 'Tangki telah dibilas bersih menggunakan solar dan dilap kering.'
print("[OK] Subtask centang selesai berhasil mengunci textarea menjadi disabled & greyed out.")

# =========================================================================
# 3. Proteksi: Subtask Selesai Menolak Modifikasi Ringkasan
# =========================================================================
print("\n--- [3/8] Proteksi Subtask Selesai: Menolak Perubahan Catatan ---")
# Via HTMX AJAX (mengembalikan 400 JSON)
res_ajax = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/summary',
    data={'summary': 'Mencoba merubah catatan saat subtask terkunci'},
    headers={'HX-Request': 'true'}
)
assert res_ajax.status_code == 400, f"Expected 400 Bad Request via AJAX, got {res_ajax.status_code}"

# Via Standard Form (mengembalikan 302 redirect)
res_form = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/summary',
    data={'summary': 'Mencoba merubah catatan saat subtask terkunci'}
)
assert res_form.status_code == 302, f"Expected 302 redirect via standard form, got {res_form.status_code}"
print("[OK] Percobaan update catatan pada subtask yang telah selesai berhasil ditolak (HTTP 400 / 302).")

# =========================================================================
# 4. Buka Centang (Uncheck) Mengaktifkan Kembali Field Catatan
# =========================================================================
print("\n--- [4/8] Buka Centang (Uncheck) Mengaktifkan Kembali Field Catatan ---")
res = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/toggle',
    headers={'HX-Request': 'true'}
)
assert res.status_code == 200
html = res.data.decode('utf-8')
assert 'disabled' not in html, "Textarea must not be disabled after uncheck"

with app.app_context():
    st = db.session.get(SubTask, subtask_id)
    assert st.is_completed is False

# Coba tulis ringkasan baru setelah di-uncheck
res = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/summary',
    data={'summary': 'Catatan diperbarui setelah uncheck: perlu cek seal pembuangan.'},
    headers={'HX-Request': 'true'}
)
assert res.status_code == 200
with app.app_context():
    st = db.session.get(SubTask, subtask_id)
    assert st.summary == 'Catatan diperbarui setelah uncheck: perlu cek seal pembuangan.'
print("[OK] Uncheck subtask sukses mengaktifkan kembali textarea dan menerima revisi catatan.")

# =========================================================================
# 5. Unggah Berkas & Foto Tingkat Tugas (Task-Level Attachments)
# =========================================================================
print("\n--- [5/8] Unggah Lampiran Tingkat Tugas (Foto & Dokumen PDF) ---")
# Upload Foto
fake_img = (io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00foto_kompresor.jpg'), 'kompresor_depan.jpg')
res_img = client.post(
    f'/tasks/{task_id}/attachments',
    data={'file': fake_img},
    content_type='multipart/form-data',
    headers={'HX-Request': 'true'}
)
assert res_img.status_code == 200
html_img = res_img.data.decode('utf-8')
assert 'kompresor_depan.jpg' in html_img
assert 'openImageLightbox' in html_img

# Upload PDF
fake_pdf = (io.BytesIO(b'%PDF-1.4 sample content manual kompresor'), 'manual_kompresor.pdf')
res_pdf = client.post(
    f'/tasks/{task_id}/attachments',
    data={'file': fake_pdf},
    content_type='multipart/form-data',
    headers={'HX-Request': 'true'}
)
assert res_pdf.status_code == 200
html_pdf = res_pdf.data.decode('utf-8')
assert 'manual_kompresor.pdf' in html_pdf

with app.app_context():
    att_photo = Attachment.query.filter_by(task_id=task_id, original_name='kompresor_depan.jpg').first()
    assert att_photo is not None
    assert att_photo.is_image is True
    assert att_photo.subtask_id is None
    assert os.path.exists(att_photo.get_absolute_path())

    att_doc = Attachment.query.filter_by(task_id=task_id, original_name='manual_kompresor.pdf').first()
    assert att_doc is not None
    assert att_doc.is_image is False
    assert os.path.exists(att_doc.get_absolute_path())
    img_id = att_photo.id
    pdf_id = att_doc.id

print("[OK] Berkas gambar dan dokumen berhasil diunggah, tersimpan di disk, dan tercatat di DB.")

# =========================================================================
# 6. Unggah Lampiran Tingkat Subtask & Sinkronisasi Silang Antar-Seksi (OOB)
# =========================================================================
print("\n--- [6/8] Unggah Lampiran Langsung pada Subtask & Sinkronisasi OOB ---")
fake_sub_img = (io.BytesIO(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfoto_tangki_oli.png'), 'foto_tangki_kuras.png')
res_sub = client.post(
    f'/tasks/{task_id}/subtasks/{subtask_id}/attachments',
    data={'file': fake_sub_img},
    content_type='multipart/form-data',
    headers={'HX-Request': 'true'}
)
assert res_sub.status_code == 200
html_sub = res_sub.data.decode('utf-8')

# Pastikan nama berkas muncul di respons subtask chips
assert 'foto_tangki_kuras.png' in html_sub
# Pastikan out-of-band swap menyertakan pembaruan ke seksi lampiran utama
assert 'attachments-section' in html_sub

with app.app_context():
    att_sub = Attachment.query.filter_by(subtask_id=subtask_id, original_name='foto_tangki_kuras.png').first()
    assert att_sub is not None
    assert att_sub.task_id == task_id
    assert att_sub.is_image is True
    sub_att_id = att_sub.id

print("[OK] Lampiran subtask berhasil diunggah dan tersinkronisasi via HTMX OOB swap.")

# =========================================================================
# 7. Endpoint Lihat Pratinjau & Unduh Lampiran
# =========================================================================
print("\n--- [7/8] Pratinjau Foto & Unduh Berkas Lampiran ---")
# Lihat foto
res_view = client.get(f'/tasks/{task_id}/attachments/{img_id}/view')
assert res_view.status_code == 200
assert 'image/jpeg' in res_view.content_type
res_view.close()

# Unduh dokumen
res_dl = client.get(f'/tasks/{task_id}/attachments/{pdf_id}/download')
assert res_dl.status_code == 200
assert 'attachment' in res_dl.headers.get('Content-Disposition', '')
assert 'manual_kompresor.pdf' in res_dl.headers.get('Content-Disposition', '')
res_dl.close()
print("[OK] Endpoint /view dan /download berjalan dengan status 200 dan header yang tepat.")

# =========================================================================
# 8. Penghapusan Lampiran & Tampilan Cetak SPK
# =========================================================================
print("\n--- [8/8] Penghapusan Lampiran Kolaboratif & Tampilan Cetak SPK ---")
with app.app_context():
    att_to_delete = db.session.get(Attachment, img_id)
    del_disk_path = att_to_delete.get_absolute_path()
    print("att_to_delete filename:", att_to_delete.filename)
    print("att_to_delete path:", del_disk_path)
    assert os.path.exists(del_disk_path)

res_del = client.post(
    f'/tasks/{task_id}/attachments/{img_id}/delete',
    headers={'HX-Request': 'true'}
)
print("res_del status:", res_del.status_code)
print("res_del body preview:", res_del.data.decode('utf-8')[:200])

with app.app_context():
    print("file exists after delete?", os.path.exists(del_disk_path))
    assert db.session.get(Attachment, img_id) is None
    assert not os.path.exists(del_disk_path), "File on disk must be removed upon attachment deletion"
print("[OK] Penghapusan berkas lampiran berhasil membersihkan database dan berkas pada disk.")

# Uji Cetak SPK (SPK Print Order)
login(admin_id)
res_print = client.get(f'/tasks/{task_id}/print')
assert res_print.status_code == 200
html_print = res_print.data.decode('utf-8')
assert 'Catatan/Hasil:' in html_print
assert 'Catatan diperbarui setelah uncheck: perlu cek seal pembuangan.' in html_print
assert 'Daftar Lampiran' in html_print
assert 'manual_kompresor.pdf' in html_print
assert 'foto_tangki_kuras.png' in html_print
print("[OK] Dokumen cetak SPK berhasil menampilkan catatan subtask dan daftar berkas lampiran.")

# =========================================================================
# Pembersihan Database & Folder Pengujian
# =========================================================================
if os.path.exists(test_upload_folder):
    shutil.rmtree(test_upload_folder, ignore_errors=True)
if os.path.exists(test_db_path):
    try:
        os.remove(test_db_path)
    except Exception:
        pass

print("\n" + "=" * 70)
print(">>> SELURUH PENGUJIAN SUBTASK SUMMARY & FILE UPLOADS BERHASIL 100%! <<<")
print("=" * 70 + "\n")
