import sys

from loguru import logger

# Remove default logger
logger.remove()

# 1) Console logging (pretty, colored)
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
           "<level>{message}</level>",
)

logger.add(
    "logs/app.log",
    level="DEBUG",
    rotation="1 day",
    retention="14 days",
    compression="zip",
    enqueue=True,
)
