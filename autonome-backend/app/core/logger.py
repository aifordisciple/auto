import sys
import os
from loguru import logger
from app.core.config import settings

# 确保日志目录存在
LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 移除默认的 handler
logger.remove()

# 1. 控制台极客输出 (带颜色和精简格式)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

# 2. 文件持久化输出 (每天滚动一次，最多保留30天，自动压缩)
logger.add(
    os.path.join(LOG_DIR, "autonome_backend.log"),
    rotation="00:00",
    retention="30 days",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
)

# 暴露给其他模块使用
log = logger
