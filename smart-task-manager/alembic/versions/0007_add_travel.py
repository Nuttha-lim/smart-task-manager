"""add trip_plans table for Travel Planning

Revision ID: 0007_add_travel
Revises: 0006_add_calendar
Create Date: 2026-08-09 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0007_add_travel'
down_revision = '0006_add_calendar'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'trip_plans',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('destination', sa.String()),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('days_json', sa.String(), nullable=True),
        sa.Column('prep_tasks_json', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('trip_plans')
