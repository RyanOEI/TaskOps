from app.extensions import db


class SubTask(db.Model):
    __tablename__ = 'subtasks'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    creator = db.relationship('User', foreign_keys=[created_by_id])
    attachments = db.relationship('Attachment', backref='subtask', cascade='all, delete-orphan', lazy='select', order_by='Attachment.created_at.desc()')

