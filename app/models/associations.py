from app.extensions import db

# Many-to-Many Association Table: User <-> Team
user_teams = db.Table(
    'user_teams',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('team_id', db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True)
)

