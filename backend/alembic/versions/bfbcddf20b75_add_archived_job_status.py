"""add archived job status

Revision ID: bfbcddf20b75
Revises: f58a83207162
Create Date: 2026-08-28 16:03:13.283709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfbcddf20b75'
down_revision: Union[str, None] = 'f58a83207162'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds "archived" to the job status enum.

    Postgres models this column as a native enum type, so a new member has to
    be declared before any row can hold it. SQLite stores the same column as
    plain text and needs nothing, which is why this branches on the dialect
    rather than emitting one statement for both.

    ADD VALUE cannot be used in the same transaction that declares it, so
    nothing here writes the new value -- existing rows keep the status they
    already have.
    """
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE statusenum ADD VALUE IF NOT EXISTS 'archived'")


def downgrade() -> None:
    """Deliberately a no-op.

    Postgres has no DROP VALUE. Removing the member means rebuilding the type
    and rewriting every row that uses it, which would silently reassign real
    user data to some other status. Leaving an unused enum member in place
    costs nothing; guessing what an archived job should become does not.
    """
