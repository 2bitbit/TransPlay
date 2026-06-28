import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import tempfile

# 日志输出目录统一采用系统安全临时目录，彻底杜绝只读 site-packages 权限崩溃
LOG_DIR = Path(tempfile.gettempdir()) / "transplay_mcp"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # Fallback to tmp dir root if subdirectory creation fails
    LOG_DIR = Path(tempfile.gettempdir())

# 使用进程 PID 命名日志文件，防止 Windows 多进程并发写入同一个日志文件时引发文件锁死锁
LOG_FILE = LOG_DIR / f"transplay_mcp_{os.getpid()}.log"

# 自动清理机制：每次有新进程启动时，自动扫描并清理旧的 PID 日志文件，只保留最近修改的 10 个，防范文件数量与磁盘空间膨胀
try:
    existing_logs = list(LOG_DIR.glob("transplay_mcp_*.log"))
    # 按修改时间从新到旧排序
    existing_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if len(existing_logs) > 10:
        for old_log in existing_logs[10:]:
            try:
                old_log.unlink()
            except Exception:
                pass
except Exception:
    pass

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
