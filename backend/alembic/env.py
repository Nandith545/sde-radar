"""Alembic environment.

The database URL comes from the app's own settings rather than alembic.ini,
so migrations always run against the same database the app does — including
on Render, where DATABASE_URL is injected at runtime and there is no .ini to
edit.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings

# Importing the models registers every table on Base.metadata, which is what
# `alembic revision --autogenerate` diffs against.
from app.database import Base
from app import models  # noqa: F401  (imported for the side effect above)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it — useful for reviewing what a
    migration will do to production before letting it near production."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Detect column type changes, not just added/dropped columns.
            compare_type=True,
            # SQLite can't ALTER most things in place; batch mode recreates the
            # table instead. Harmless on Postgres, essential for local SQLite.
            render_as_batch=settings.database_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
