from logging.config import fileConfig
import os
import asyncio

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from dotenv import load_dotenv

# Load .env
load_dotenv()

config = context.config

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 🔥 Import your Base metadata here
from database.models import Base  # adjust if needed

target_metadata = Base.metadata

# 🔥 Get DATABASE_URL from .env
database_url = os.getenv("DATABASE_URL","")

if not database_url:
    raise ValueError("DATABASE_URL not found in .env")


# -----------------------------
# OFFLINE MODE
# -----------------------------
def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# -----------------------------
# ONLINE MODE (ASYNC)
# -----------------------------
def do_run_migrations(connection: Connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# -----------------------------
# ENTRY POINT
# -----------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())