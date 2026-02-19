"""Redis caching layer — cache tool results to reduce external API calls."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from evidentia.core.config import get_settings
from evidentia.core.logging import get_logger

logger = get_logger(__name__)

_redis_client = None


async def get_redis():
    """Get or create a Redis client (lazy init)."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            settings = get_settings()
            _redis_client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Verify connectivity
            await _redis_client.ping()
            logger.info("redis_connected")
        except Exception as exc:
            logger.warning("redis_unavailable", error=str(exc))
            _redis_client = None
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("redis_disconnected")


async def check_redis() -> bool:
    """Return True if Redis is reachable."""
    try:
        client = await get_redis()
        if client is None:
            return False
        await client.ping()
        return True
    except Exception:
        return False


class RedisCache:
    """Cache with TTL for tool results."""

    # TTLs in seconds
    TOOL_TTL = 3600       # 1 hour for search results
    DOI_TTL = 86400       # 24 hours for DOI lookups
    DEFAULT_TTL = 1800    # 30 minutes default

    TOOL_TTLS: dict[str, int] = {
        "arxiv_search": TOOL_TTL,
        "semantic_scholar": TOOL_TTL,
        "web_search": TOOL_TTL,
        "doi_lookup": DOI_TTL,
    }

    @staticmethod
    def _cache_key(tool_name: str, input_data: dict[str, Any]) -> str:
        """Generate a deterministic cache key from tool name + input."""
        input_str = json.dumps(input_data, sort_keys=True)
        digest = hashlib.sha256(f"{tool_name}:{input_str}".encode()).hexdigest()[:16]
        return f"evidentia:tool:{tool_name}:{digest}"

    @staticmethod
    async def get(tool_name: str, input_data: dict[str, Any]) -> dict[str, Any] | None:
        """Get cached tool result, or None if miss."""
        client = await get_redis()
        if client is None:
            return None

        key = RedisCache._cache_key(tool_name, input_data)
        try:
            cached = await client.get(key)
            if cached:
                logger.debug("cache_hit", tool=tool_name, key=key)
                return json.loads(cached)
        except Exception as exc:
            logger.warning("cache_get_error", error=str(exc))

        return None

    @staticmethod
    async def set(tool_name: str, input_data: dict[str, Any], result: dict[str, Any]) -> None:
        """Cache a tool result with appropriate TTL."""
        client = await get_redis()
        if client is None:
            return

        key = RedisCache._cache_key(tool_name, input_data)
        ttl = RedisCache.TOOL_TTLS.get(tool_name, RedisCache.DEFAULT_TTL)

        try:
            await client.setex(key, ttl, json.dumps(result, default=str))
            logger.debug("cache_set", tool=tool_name, key=key, ttl=ttl)
        except Exception as exc:
            logger.warning("cache_set_error", error=str(exc))
