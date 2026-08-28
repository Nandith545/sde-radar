"""Guards on the migration files themselves.

Three separate revisions in a row shipped a NOT NULL column with no
server_default, because that is exactly what `alembic revision --autogenerate`
emits and its "please adjust!" comment is easy to skip. Each one passed every
test and `alembic check`, because the test databases are created empty --
the failure only appears against a table that already has rows, which in
practice means production.

This reads the migration scripts as text rather than running them, so it
catches the mistake at the point it is written.
"""

import pathlib
import re

VERSIONS = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"

# add_column(sa.Column('x', sa.Type(), nullable=False, ...)) -- one call, which
# may span lines. Non-greedy up to the first closing paren pair.
_ADD_COLUMN = re.compile(r"add_column\(\s*sa\.Column\((.*?)\)\s*\)", re.DOTALL)


def _add_column_calls() -> list[tuple[str, str]]:
    calls = []
    for path in sorted(VERSIONS.glob("*.py")):
        source = path.read_text()
        # Only the upgrade path matters; downgrade drops columns.
        upgrade = source.split("def downgrade")[0]
        for match in _ADD_COLUMN.finditer(upgrade):
            calls.append((path.name, " ".join(match.group(1).split())))
    return calls


def test_migration_files_exist() -> None:
    """Guards the guard: a bad glob would make every assertion below vacuous."""
    assert _add_column_calls(), "found no add_column calls to check"


def test_not_null_columns_are_added_with_a_server_default() -> None:
    """A NOT NULL column with nothing to backfill fails on a populated table.

    Postgres cannot invent a value for rows that already exist, so the
    migration aborts and -- because the container runs `alembic upgrade head`
    before uvicorn -- the deploy never starts. Add `server_default=...`, or
    make the column nullable and mean it.
    """
    offenders = [
        f"{name}: sa.Column({args})"
        for name, args in _add_column_calls()
        if "nullable=False" in args and "server_default" not in args
    ]
    assert not offenders, (
        "These columns are NOT NULL with no server_default and will fail "
        "against a table that already has rows:\n  " + "\n  ".join(offenders)
    )
