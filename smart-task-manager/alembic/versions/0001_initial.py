"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-08-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('base_points', sa.Integer(), nullable=True),
        sa.Column('estimated_time', sa.Integer(), nullable=True),
        sa.Column('deadline', sa.DateTime(), nullable=True),
        sa.Column('deadline_time', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('goal_id', sa.String(), nullable=True),
        sa.Column('last_deadline_check', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'energy_logs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('energy_level', sa.Integer(), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('value', sa.String(), nullable=True),
    )

    op.create_table(
        'goals',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('desire_score', sa.Integer(), nullable=True),
        sa.Column('urgency_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'rewards',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('point_cost', sa.Integer(), nullable=False),
        sa.Column('locked', sa.Boolean(), nullable=True),
    )

    op.create_table(
        'spell_exceptions',
        sa.Column('word', sa.String(), primary_key=True),
    )


def downgrade():
    op.drop_table('spell_exceptions')
    op.drop_table('rewards')
    op.drop_table('goals')
    op.drop_table('app_settings')
    op.drop_table('energy_logs')
    op.drop_table('tasks')
