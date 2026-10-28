from datetime import datetime, timezone
from app.extensions import db
from app.models.enums import ItemStatus


class ItemRequest(db.Model):
    __tablename__ = 'item_requests'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum(ItemStatus), default=ItemStatus.REQUESTED, nullable=False)
    rejection_reason = db.Column(db.Text, nullable=True)

    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ordered_at = db.Column(db.DateTime, nullable=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)

