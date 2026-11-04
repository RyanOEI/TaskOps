from datetime import datetime, timezone
from app.extensions import db


class Attachment(db.Model):
    __tablename__ = 'attachments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    subtask_id = db.Column(db.Integer, db.ForeignKey('subtasks.id'), nullable=True, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    filename = db.Column(db.String(255), nullable=False)        # Nama berkas di disk: <uuid>_<clean_name>
    original_name = db.Column(db.String(255), nullable=False)   # Nama asli yang ditampilkan
    file_size = db.Column(db.Integer, nullable=False)           # Ukuran dalam bytes
    mime_type = db.Column(db.String(100), nullable=False)       # e.g. 'image/png', 'application/pdf'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    uploader = db.relationship('User', foreign_keys=[uploaded_by_id])

    @property
    def is_image(self) -> bool:
        if self.mime_type and self.mime_type.startswith('image/'):
            return True
        return self.original_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))

    @property
    def file_size_formatted(self) -> str:
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.1f} MB"

    def get_absolute_path(self) -> str:
        import os
        from flask import current_app
        upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.instance_path, 'uploads'))
        return os.path.join(upload_folder, self.filename)
