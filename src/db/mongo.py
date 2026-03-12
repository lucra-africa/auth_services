"""MongoDB connection — Atlas cluster."""

import logging
import re

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def _mask_uri(uri: str) -> str:
    """Hide credentials in log output."""
    return re.sub(r"://[^@]+@", "://***:***@", uri)


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where(),
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def init_database() -> None:
    """Connect to MongoDB Atlas and ensure indexes."""
    global _client
    _client = get_client()
    await _client[settings.mongo_db].command("ping")
    logger.info("Connected to MongoDB: %s", _mask_uri(settings.mongo_uri))

    from src.db.indexes import ensure_indexes
    await ensure_indexes(get_db())


async def close_database() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        _active_uri = None


async def get_fallback_db() -> AsyncIOMotorDatabase | None:
    """Return a database handle to the fallback URI, or None if not configured."""
    if not settings.mongo_uri_fallback:
        return None
    try:
        client = AsyncIOMotorClient(settings.mongo_uri_fallback, serverSelectionTimeoutMS=5000)
        await client[settings.mongo_db].command("ping")
        return client[settings.mongo_db]
    except Exception as exc:
        logger.warning("Fallback MongoDB unavailable: %s", exc)
        return None
