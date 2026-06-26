import logging
from pathlib import Path

# Log file path: src/transplay_mcp/transplay_mcp.log
LOG_FILE = Path(__file__).resolve().parent.parent / "transplay_mcp.log"

logger = logging.getLogger("transplay_mcp")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s"
    )
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console/Stderr handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

logger.info(f"Logging system initialized. Output file: {LOG_FILE}")
