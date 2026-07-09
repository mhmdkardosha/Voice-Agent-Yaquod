import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["YAQUOD_API_KEY"] = "test-api-key"

os.environ["MQTT_HOST"] = "localhost"
os.environ["MQTT_PORT"] = "1883"
os.environ["MQTT_USERNAME"] = ""
os.environ["MQTT_PASSWORD"] = ""