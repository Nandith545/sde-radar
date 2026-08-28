"""add target_country and work_mode to users

Revision ID: 16aba3108448
Revises: 094413d4e88d
Create Date: 2026-08-27 23:14:55.794075

Both columns carry a server_default. Autogenerate emitted them as plain
NOT NULL, which works against an empty table and fails against a populated
one -- Postgres cannot backfill existing rows with a value the migration
never supplies, and production already has users. The default is left on the
column rather than dropped afterwards: the model sets its own Python-side
default for new rows, so the two agree, and keeping it means a future insert
that bypasses the ORM cannot violate the constraint either.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16aba3108448'
down_revision: Union[str, None] = '094413d4e88d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('target_country', sa.String(length=100), nullable=False, server_default='')
        )
        batch_op.add_column(
            sa.Column('work_mode', sa.String(length=20), nullable=False, server_default='')
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('work_mode')
        batch_op.drop_column('target_country')
