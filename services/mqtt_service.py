import asyncio
import json
import logging
import os
import ssl

import aiomqtt

from config.redis_db import get_redis

from .data_handling_service import handle_vehicle_message

logger = logging.getLogger("yaquod-agent")


class CentralMQTTService:
    def __init__(self):
        self.client = None
        self.r_client = None
        self._runner_task = None

    def start(self):
        if self._runner_task is None or self._runner_task.done():
            self._runner_task = asyncio.create_task(self._connect_and_run())
            logger.info("[Central MQTT] Background task started.")

    async def _connect_and_run(self):
        if self.r_client is None:
            self.r_client = get_redis()

        mqtt_host = os.environ.get("MQTT_HOST", "localhost")
        mqtt_port = int(os.environ.get("MQTT_PORT", 1883))
        mqtt_username = os.environ.get("MQTT_USERNAME", "")
        mqtt_password = os.environ.get("MQTT_PASSWORD", "")
        use_ssl = os.environ.get("MQTT_SSL", "false").lower() == "true"
        tls_context = ssl.create_default_context() if use_ssl else None

        while True:
            try:
                logger.info(f"[Central MQTT] Connecting to broker at {mqtt_host}:{mqtt_port}...")
                async with aiomqtt.Client(
                    hostname=mqtt_host,
                    port=mqtt_port,
                    username=mqtt_username if mqtt_username else None,
                    password=mqtt_password if mqtt_password else None,
                    tls_context=tls_context,
                ) as client:
                    self.client = client
                    logger.info("[Central MQTT] Connected successfully!")
                    await client.subscribe("vehicle/+/state")
                    await client.subscribe("vehicle/+/location")
                    logger.info("[Central MQTT] Subscribed to vehicle/+/state AND location")

                    async for message in client.messages:
                        await handle_vehicle_message(
                            message.topic.value, message.payload, self.r_client
                        )
            except asyncio.CancelledError:
                logger.info("[Central MQTT] Connection task cancelled.")
                break
            except Exception as e:
                logger.error(f"[Central MQTT] Connection error: {e}. Reconnecting in 5 seconds...")
                self.client = None
                await asyncio.sleep(5)

    async def publish_action(self, car_id: str, topic_suffix: str, payload: dict):
        if not self.client:
            logger.error(f"[Central MQTT] Cannot publish. Client not connected. Car: {car_id}")
            return False
        try:
            topic = f"vehicle/{car_id}/{topic_suffix}"
            await self.client.publish(topic, json.dumps(payload))
            logger.info(f"[Central MQTT] Published to {topic}")
            return True
        except Exception as e:
            logger.error(f"[Central MQTT] Publish error on {topic}: {e}")
            return False


central_mqtt = CentralMQTTService()
