"""add address and phone to users

Revision ID: dc505eab741c
Revises: 59d5b47f64c9
Create Date: 2026-08-27 23:58:09.081915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc505eab741c'
down_revision: Union[str, None] = '59d5b47f64c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default on both, as with every NOT NULL column added since the
    # initial schema: autogenerate omits it, which passes against an empty
    # table and fails against production the moment a row exists.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address', sa.String(length=500), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('phone', sa.String(length=50), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('phone')
        batch_op.drop_column('address')
