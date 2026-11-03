"""add notifications table

Revision ID: 0002_add_notifications
Revises: 0001_initial
Create Date: 2026-08-06 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_notifications'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('urgency', sa.String(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('notifications')
