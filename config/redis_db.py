import logging
import redis

logger = logging.getLogger("yaquod-api")

redis_client: redis.Redis = None

def init_redis():
    global redis_client
    try:
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_client.ping()
        logger.info("Successfully connected to Redis Server.")
    except redis.ConnectionError:
        logger.error("Failed to connect to Redis. Make sure Redis is running!")
        redis_client = None

def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        logger.info("Redis client not initialized yet. Initializing now...")
        init_redis()       
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized or running.")
        
    return redis_client