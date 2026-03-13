# utils.py
from pathlib import Path
import logging
from typing import Dict, Any

# Define the directory for saving uploaded files
file_saver = Path("./uploads")

# Dictionary to store active sessions and their contexts
# Structure: {session_id: {"ws": WebSocket, "queue": LiveRequestQueue, "task": asyncio.Task, "context": Dict[str, Any], "last_upload": Dict[str, Any], "run_config": RunConfig}}
active_sessions: Dict[str, Dict[str, Any]] = {}

# Configure the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a console handler and set the level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create a formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add the handler to the logger only if it doesn't already have handlers
# This prevents duplicate logging if the module is imported multiple times or if main.py also configures logging.
if not logger.handlers:
    logger.addHandler(console_handler)
    logger.info("Logger configured.")
else:
    logger.info("Logger already configured.")


# Ensure the upload directory exists on startup
try:
    file_saver.mkdir(exist_ok=True)
    logger.info(f"Upload directory created or already exists: {file_saver}")
except Exception as e:
    logger.error(f"Failed to create upload directory {file_saver}: {e}")
