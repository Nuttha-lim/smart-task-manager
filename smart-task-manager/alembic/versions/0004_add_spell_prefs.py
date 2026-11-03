"""add spell_prefs table

Revision ID: 0004_add_spell_prefs
Revises: 0003_add_devices
Create Date: 2026-08-09 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_add_spell_prefs'
down_revision = '0003_add_devices'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'spell_prefs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('word', sa.String(), nullable=False),
        sa.Column('corrected', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('spell_prefs')
