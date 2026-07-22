"""meter analysis, not writing

The allowance was shared between editing the text and re-running the analysis.
Real use showed that's the wrong thing to charge for: a day gets written in
passes — a note at lunch, the rest at midnight — and counting those punishes
keeping up with your own day. Writing costs nothing to store, so it is free
now. The analysis is what spends a model call, and what should settle once the
day is actually over, so the allowance moves entirely onto it.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("entries", "edit_count", new_column_name="analysis_count")
    # The counts already stored were edits, not analyses. Nobody has analysed a
    # day yet, so carrying them over would hand people a bill for writing.
    op.execute("UPDATE entries SET analysis_count = 0")


def downgrade() -> None:
    op.alter_column("entries", "analysis_count", new_column_name="edit_count")
