import sys
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["YAQUOD_API_KEY"] = "test-api-key"