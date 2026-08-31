"""add target_states to users

Revision ID: a5f4f6f8a892
Revises: 0502cecd2127
Create Date: 2026-08-31 14:41:34.957481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5f4f6f8a892'
down_revision: Union[str, None] = '0502cecd2127'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the state/province preference, defaulting every existing user to
    "all states".

    server_default is set by hand -- autogenerate omits it, and a NOT NULL
    column added without one fails outright against a users table that
    already has rows, which is every environment except a fresh install.

    An empty list is the right backfill and not merely a safe one: nobody has
    ever narrowed by state, so "all of them" is what they currently have.
    """
    op.add_column(
        "users",
        sa.Column("target_states", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("users", "target_states")
