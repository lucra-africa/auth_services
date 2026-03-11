"""MongoDB connection with automatic failover between primary and fallback."""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_active_uri: str | None = None


async def _try_connect(uri: str, label: str) -> AsyncIOMotorClient:
    """Attempt to connect and ping a MongoDB URI. Raises on failure."""
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    await client[settings.mongo_db].command("ping")
    logger.info("Connected to %s MongoDB: %s", label, _mask_uri(uri))
    return client


def _mask_uri(uri: str) -> str:
    """Hide credentials in log output."""
    import re
    return re.sub(r"://[^@]+@", "://***:***@", uri)


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def init_database() -> None:
    """Connect to primary MongoDB; fall back to Atlas if primary is down."""
    global _client, _active_uri

    # Try primary
    try:
        _client = await _try_connect(settings.mongo_uri, "primary")
        _active_uri = settings.mongo_uri
    except Exception as exc:
        logger.warning("Primary MongoDB unavailable: %s", exc)

        if not settings.mongo_uri_fallback:
            raise RuntimeError("Primary MongoDB is down and no fallback URI configured") from exc

        # Try fallback
        try:
            _client = await _try_connect(settings.mongo_uri_fallback, "fallback")
            _active_uri = settings.mongo_uri_fallback
        except Exception as fb_exc:
            raise RuntimeError("Both primary and fallback MongoDB are unreachable") from fb_exc

    from src.db.indexes import ensure_indexes
    await ensure_indexes(get_db())


async def close_database() -> None:
    global _client, _active_uri
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
