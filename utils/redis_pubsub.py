import asyncio
import json
import logging

import redis.asyncio as redis

logger = logging.getLogger("yaquod-api")

REDIS_CHANNEL = "vehicle_events"

redis_client = None
_listener_task = None


async def publish_event(event: dict):
    await redis_client.publish(REDIS_CHANNEL, json.dumps(event))


async def publish(name: str, model):
    await publish_event({
        "event": name,
        "data": model.model_dump(),
    })


async def redis_listener(manager):
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                payload = json.loads(message["data"])
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring malformed Redis payload: %r",
                    message["data"],
                )
                continue

            await manager.local_broadcast(payload)

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL)
        await pubsub.close()


async def startup_redis(redis_url: str, manager):
    global redis_client, _listener_task

    redis_client = redis.from_url(
        redis_url,
        decode_responses=True,
    )

    await redis_client.ping()

    _listener_task = asyncio.create_task(redis_listener(manager))


async def shutdown_redis():
    if _listener_task:
        _listener_task.cancel()
        await asyncio.gather(
            _listener_task,
            return_exceptions=True,
        )

    if redis_client:
        await redis_client.close()
