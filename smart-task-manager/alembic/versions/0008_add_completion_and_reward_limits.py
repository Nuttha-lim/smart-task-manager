"""add task completion + reward limit columns

Revision ID: 0008_add_columns
Revises: 0007_add_travel
Create Date: 2026-08-09 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0008_add_columns'
down_revision = '0007_add_travel'
branch_labels = None
depends_on = None


def upgrade():
    # tasks: คอลัมน์เก็บเวลาที่ทำเสร็จ + แต้มที่ให้ (ใช้ undo/streak ใหม่)
    op.add_column('tasks', sa.Column('completed_at', sa.DateTime(), nullable=True))
    op.add_column('tasks', sa.Column('points_awarded', sa.Integer(), nullable=True))

    # rewards: จำกัดสิทธิ์ต่อวัน/เดือน/ปี + แหล่งที่มา (user/ai) + เวลาสร้าง
    op.add_column('rewards', sa.Column('max_per_day', sa.Integer(), nullable=True))
    op.add_column('rewards', sa.Column('max_per_month', sa.Integer(), nullable=True))
    op.add_column('rewards', sa.Column('max_per_year', sa.Integer(), nullable=True))
    op.add_column('rewards', sa.Column('source', sa.String(), nullable=True))
    op.add_column('rewards', sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('rewards', 'created_at')
    op.drop_column('rewards', 'source')
    op.drop_column('rewards', 'max_per_year')
    op.drop_column('rewards', 'max_per_month')
    op.drop_column('rewards', 'max_per_day')
    op.drop_column('tasks', 'points_awarded')
    op.drop_column('tasks', 'completed_at')
