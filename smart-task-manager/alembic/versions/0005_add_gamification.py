"""add achievements tables

Revision ID: 0005_add_gamification
Revises: 0004_add_spell_prefs
Create Date: 2026-08-09 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005_add_gamification'
down_revision = '0004_add_spell_prefs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'achievements',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('key', sa.String(), unique=True),
        sa.Column('title', sa.String()),
        sa.Column('description', sa.String()),
        sa.Column('icon', sa.String()),
        sa.Column('points', sa.Integer(), nullable=True),
        sa.Column('condition_type', sa.String()),
        sa.Column('condition_value', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'unlocked_achievements',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('achievement_key', sa.String()),
        sa.Column('unlocked_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('unlocked_achievements')
    op.drop_table('achievements')
