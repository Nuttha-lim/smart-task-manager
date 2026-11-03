"""add timetable_cancels table for per-day class cancellation

Revision ID: 0011_add_timetable_cancels
Revises: 0010_add_routines
Create Date: 2026-08-09 23:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0011_add_timetable_cancels'
down_revision = '0010_add_routines'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'timetable_cancels',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('timetable_cancels')
