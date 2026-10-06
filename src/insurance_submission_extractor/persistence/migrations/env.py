"""Alembic environment.

Used in two ways: programmatically by DatabaseStore.migrate (which hands over an
open connection) and from the command line (`alembic -c alembic.ini ...`), where
the URL comes from DATABASE_URL.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from insurance_submission_extractor.persistence.models import Base
from insurance_submission_extractor.persistence.store import normalize_database_url

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")

    if not url:
        from insurance_submission_extractor.config import Settings

        url = Settings().database_url

    if not url:
        raise SystemExit("Set DATABASE_URL (or sqlalchemy.url) before running migrations.")

    return normalize_database_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")

    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_database_url())
    with engine.begin() as new_connection:
        context.configure(connection=new_connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
