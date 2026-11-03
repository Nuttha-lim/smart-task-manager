"""add devices table

Revision ID: 0003_add_devices
Revises: 0002_add_notifications
Create Date: 2026-08-06 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_devices'
down_revision = '0002_add_notifications'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'devices',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('device_token', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('devices')
