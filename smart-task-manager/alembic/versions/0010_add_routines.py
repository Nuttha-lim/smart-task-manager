"""add routines table for daily routines

Revision ID: 0010_add_routines
Revises: 0009_add_goal_target_date
Create Date: 2026-08-09 22:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_add_routines'
down_revision = '0009_add_goal_target_date'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'routines',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('time', sa.String(length=5), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('description', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('routines')
