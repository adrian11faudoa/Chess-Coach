"""Logging setup for ChessCoach."""

import logging
import os
from pathlib import Path


def setup_logger(name: str = "chesscoach", level: int = logging.DEBUG) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    try:
        if os.name == "nt":
            log_dir = Path(os.environ.get("APPDATA", Path.home())) / "ChessCoach"
        else:
            log_dir = Path.home() / ".config" / "ChessCoach"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "chesscoach.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass

    return logger


def get_logger(module: str) -> logging.Logger:
    """Get a child logger for a specific module."""
    return logging.getLogger(f"chesscoach.{module}")
