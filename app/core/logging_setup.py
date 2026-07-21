"""
app.core.logging_setup
=======================
Centralized Loguru configuration. Call `configure_logging()` exactly once,
as early as possible in main.py, before any other application module logs
anything.

Produces:
  logs/app_YYYY-MM-DD.log      -- rotating daily, INFO and above
  logs/errors_YYYY-MM-DD.log   -- rotating daily, ERROR and above only
  console (stdout)             -- DEBUG and above, colorized, dev-only
"""

from __future__ import annotations

import sys

from loguru import logger

from app.core import paths


def configure_logging(*, console: bool = True, debug: bool = False) -> None:
    logger.remove()  # drop Loguru's default handler so we control format fully

    log_dir = paths.logs_dir()

    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        level="INFO",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,  # thread/process-safe -- critical since workers log too
        backtrace=False,
        diagnose=False,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
    )

    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
    )

    if console:
        logger.add(
            sys.stdout,
            level="DEBUG" if debug else "INFO",
            colorize=True,
            format=(
                "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
            ),
        )

    logger.info("Logging initialized. Log directory: {}", log_dir)
