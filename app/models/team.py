from app.extensions import db
from app.models.associations import user_teams


class Team(db.Model):
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    members = db.relationship('User', secondary=user_teams, back_populates='teams')
    tasks = db.relationship('Task', backref='assigned_team', lazy='dynamic')

    @property
    def active_members(self):
        """Returns the team's active members only."""
        return [m for m in self.members if m.is_active]


def has_team_history(team: Team) -> bool:
    """Check whether a team has historical or active assigned tasks."""
    if not team:
        return False
    from app.models.task import Task
    return Task.query.filter_by(assigned_team_id=team.id).first() is not None

