"""add holidays + class schedules tables

Revision ID: 0006_add_calendar
Revises: 0005_add_gamification
Create Date: 2026-08-09 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_add_calendar'
down_revision = '0005_add_gamification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'holidays',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('name', sa.String()),
        sa.Column('kind', sa.String(), default='public'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'class_schedules',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('day_of_week', sa.Integer()),
        sa.Column('start_time', sa.String()),
        sa.Column('end_time', sa.String()),
        sa.Column('subject', sa.String()),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('class_schedules')
    op.drop_table('holidays')
