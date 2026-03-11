"""MongoDB connection — singleton Motor client matching poruta-backend patterns."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def init_database() -> None:
    """Called on app startup — warms the connection and creates indexes."""
    db = get_db()
    await db.command("ping")

    from src.db.indexes import ensure_indexes
    await ensure_indexes(db)


async def close_database() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
