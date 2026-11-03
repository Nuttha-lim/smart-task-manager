"""add goals.target_date for Exam-Prep / long-term study scheduling

Revision ID: 0009_add_goal_target_date
Revises: 0008_add_columns
Create Date: 2026-08-09 23:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_add_goal_target_date'
down_revision = '0008_add_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('goals', sa.Column('target_date', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('goals', 'target_date')
