"""add seniority and min_salary to users

Revision ID: 59d5b47f64c9
Revises: 16aba3108448
Create Date: 2026-08-27 23:26:48.472643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59d5b47f64c9'
down_revision: Union[str, None] = '16aba3108448'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # seniority carries a server_default for the same reason as the previous
    # revision: autogenerate emits NOT NULL with nothing to backfill existing
    # rows, which passes against an empty table and fails against production.
    # min_salary is nullable on purpose -- NULL is "no floor", which is a
    # different statement from a floor of zero.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('seniority', sa.String(length=20), nullable=False, server_default='')
        )
        batch_op.add_column(sa.Column('min_salary', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('min_salary')
        batch_op.drop_column('seniority')
