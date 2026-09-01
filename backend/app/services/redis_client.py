from functools import lru_cache

import redis

from app.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """A cached, process-wide client - redis-py's client already pools
    connections internally, so there's no need to build a fresh one per
    call the way get_xrpl_client() does for the stateless XRPL HTTP client.
    """
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
