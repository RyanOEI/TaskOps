import re
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db
from app.models.enums import RoleEnum
from app.models.associations import user_teams

E164_REGEX = re.compile(r'^\+[1-9]\d{6,14}$')
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_.]{3,30}$')


def validate_username(username: str) -> bool:
    """Validate username: alphanumeric, dot, underscore, 3-30 characters."""
    if not username:
        return False
    return bool(USERNAME_REGEX.match(username.strip()))


def validate_e164_phone(phone: str) -> bool:
    """Validate that phone number conforms strictly to international E.164 format."""
    if not phone:
        return True
    return bool(E164_REGEX.match(phone.strip()))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    phone_number = db.Column(db.String(30), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(RoleEnum), default=RoleEnum.STAFF, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    teams = db.relationship('Team', secondary=user_teams, back_populates='members')
    created_tasks = db.relationship('Task', foreign_keys='Task.created_by_id', backref='creator', lazy='dynamic')
    assigned_tasks = db.relationship('Task', foreign_keys='Task.assigned_user_id', backref='assigned_user', lazy='dynamic')
    item_requests = db.relationship('ItemRequest', foreign_keys='ItemRequest.requested_by_id', backref='requester', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    push_subscriptions = db.relationship('PushSubscription', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == RoleEnum.ADMIN

    @property
    def active_teams(self):
        """Returns the user's active teams only."""
        return [t for t in self.teams if t.is_active]


def has_user_history(user: User) -> bool:
    """Check whether a user has historical task or material request ties."""
    if not user:
        return False
    from app.models.task import Task
    from app.models.item_request import ItemRequest

    has_created = Task.query.filter_by(created_by_id=user.id).first() is not None
    has_assigned = Task.query.filter_by(assigned_user_id=user.id).first() is not None
    has_requests = ItemRequest.query.filter_by(requested_by_id=user.id).first() is not None
    return has_created or has_assigned or has_requests

