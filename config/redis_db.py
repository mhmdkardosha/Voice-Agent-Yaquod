import logging
import os

import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("yaquod-api")

redis_client: redis.Redis = None


def init_redis():
    global redis_client

    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        logger.warning("REDIS_URL is not set")
        redis_client = None
        return
    try:
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
        )
        redis_client.ping()
        logger.info("Successfully connected to Redis Server.")
    except redis.ConnectionError:
        logger.error("Failed to connect to Redis")
        redis_client = None


def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        logger.info("Redis client not initialized yet. Initializing now...")
        init_redis()
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")

    return redis_client
