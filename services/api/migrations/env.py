"""Async Alembic environment shared by local and Demo migrations."""

import asyncio
import os

from alembic import context
from services.api.app.persistence import models  # noqa: F401
from services.api.app.persistence.database.base import Base
from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table, inspect, pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _prepare_version_table(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return

    if inspect(connection).has_table("alembic_version"):
        connection.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
        )
        return

    version_table = Table(
        "alembic_version",
        MetaData(),
        Column("version_num", String(255), nullable=False),
        PrimaryKeyConstraint("version_num", name="alembic_version_pkc"),
    )
    version_table.create(connection)


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    _prepare_version_table(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
