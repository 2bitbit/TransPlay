import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 使用进程 PID 命名日志文件，防止 Windows 多进程并发写入同一个日志文件时引发文件锁死锁
LOG_FILE = Path(__file__).resolve().parent.parent / f"transplay_mcp_{os.getpid()}.log"

logger = logging.getLogger("transplay_mcp")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s"
    )
    
    # File handler with rotation (max 5MB per file, max 3 backups per process)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console/Stderr handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

logger.info(f"Logging system initialized for PID {os.getpid()}. Output file: {LOG_FILE}")
