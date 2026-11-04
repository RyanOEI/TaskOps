"""Add priority, is_archived, completion_remarks, rejection_reason, and task_activities

Revision ID: a1b2c3d4e5f6
Revises: 4121fbea8376
Create Date: 2026-10-26 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '4121fbea8376'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add columns to tasks
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('priority', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'URGENT', name='taskpriority'), server_default='MEDIUM', nullable=False))
        batch_op.add_column(sa.Column('is_archived', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('completion_remarks', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_tasks_is_archived'), ['is_archived'], unique=False)

    # 2. Add column to item_requests
    with op.batch_alter_table('item_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))

    # 3. Create task_activities table
    op.create_table(
        'task_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('task_activities')

    with op.batch_alter_table('item_requests', schema=None) as batch_op:
        batch_op.drop_column('rejection_reason')

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_is_archived'))
        batch_op.drop_column('completion_remarks')
        batch_op.drop_column('is_archived')
        batch_op.drop_column('priority')

