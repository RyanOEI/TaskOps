from datetime import datetime, timezone, date
from app.extensions import db
from app.models.enums import TaskStatus, TaskPriority


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    priority = db.Column(db.Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    status = db.Column(db.Enum(TaskStatus), default=TaskStatus.TODO, nullable=False, index=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    pending_reason = db.Column(db.Text, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    completion_remarks = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    subtasks = db.relationship('SubTask', backref='task', cascade='all, delete-orphan', lazy='select')
    item_requests = db.relationship('ItemRequest', backref='task', cascade='all, delete-orphan', lazy='select')
    activities = db.relationship('TaskActivity', backref='task', cascade='all, delete-orphan', lazy='select', order_by='TaskActivity.created_at.desc()')
    attachments = db.relationship('Attachment', backref='task', cascade='all, delete-orphan', lazy='select', order_by='Attachment.created_at.desc()')

    @property
    def is_overdue(self) -> bool:
        if self.due_date and not self.is_archived and self.status != TaskStatus.COMPLETED:
            return self.due_date < date.today()
        return False


def is_authorized_for_task(user, task) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_admin:
        return True
    if task.assigned_user_id == user.id:
        return True
    if task.assigned_team_id and (task.assigned_team in user.active_teams):
        return True
    if task.created_by_id == user.id:
        return True
    return False

