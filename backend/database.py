import logging

from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    # Import models here to avoid circular dependency
    from backend.models import User

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns introduced after initial schema (SQLite doesn't support
        # ALTER TABLE ADD COLUMN IF NOT EXISTS, so we catch and ignore errors)
        migrations = [
            "ALTER TABLE agent_registrations ADD COLUMN display_name TEXT NOT NULL DEFAULT ''",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except OperationalError as e:
                logger.info(f"Migration skipped (likely already applied): {sql} - {e}")

        # Deduplicate users by email — keep oldest, delete the rest
        await conn.execute(text("""
            DELETE FROM users
            WHERE id NOT IN (
                SELECT MIN(id) FROM users GROUP BY email
            )
        """))

        # Deduplicate agent_registrations per user — keep most recent
        await conn.execute(text("""
            DELETE FROM agent_registrations
            WHERE id NOT IN (
                SELECT id FROM agent_registrations ar1
                WHERE created_at = (
                    SELECT MAX(created_at) FROM agent_registrations ar2
                    WHERE ar2.user_id = ar1.user_id
                )
            )
        """))

        # Remove stale test users (integration test cleanup that didn't complete)
        await conn.execute(
            delete(User).where(User.email.like("inttest-%@example.com"))
        )
        await conn.execute(
            delete(User).where(User.email == "smoke-test@example.com")
        )


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session
