import json
import logging
import os

import redis

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True,
)


def cache_get(key: str):
    try:
        value = redis_client.get(key)

        if value is None:
            logger.info(f"Cache MISS for {key}")
            return None

        logger.info(f"Cache HIT for {key}")
        return json.loads(value)

    except Exception as e:
        logger.error(f"Redis unavailable during GET for key={key}: {e}")
        return None


def cache_set(key: str, value, ttl: int = 30):
    try:
        redis_client.set(key, json.dumps(value, default=str), ex=ttl)

    except Exception as e:
        logger.error(f"Redis unavailable during SET for key={key}: {e}")


def cache_clear_all():
    try:
        redis_client.flushdb()
        logger.info("Cache cleared")

    except Exception as e:
        logger.error(f"Redis unavailable during cache clear: {e}")