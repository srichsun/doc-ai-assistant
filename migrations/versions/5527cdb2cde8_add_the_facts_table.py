"""add the facts table

Revision ID: 5527cdb2cde8
Revises: 6d7980810396
Create Date: 2026-07-21 14:12:16.799139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5527cdb2cde8'
down_revision: Union[str, Sequence[str], None] = '6d7980810396'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'facts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_facts_category'), 'facts', ['category'], unique=False)
    op.create_index(op.f('ix_facts_created_at'), 'facts', ['created_at'], unique=False)
    op.create_index(op.f('ix_facts_entry_id'), 'facts', ['entry_id'], unique=False)
    op.create_index(op.f('ix_facts_user_id'), 'facts', ['user_id'], unique=False)
    # Autogenerate also proposed dropping entries.mood/wins/themes and making
    # entries.user_id NOT NULL. Both are deliberately left out: the old columns
    # still hold the only copy of past wins until scripts/backfill_facts.py has
    # re-extracted them, and existing rows have NULL user_id, so the NOT NULL
    # would fail. Each belongs in its own migration, once its data is ready.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_facts_user_id'), table_name='facts')
    op.drop_index(op.f('ix_facts_entry_id'), table_name='facts')
    op.drop_index(op.f('ix_facts_created_at'), table_name='facts')
    op.drop_index(op.f('ix_facts_category'), table_name='facts')
    op.drop_table('facts')
