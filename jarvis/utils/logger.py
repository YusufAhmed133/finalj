"""Centralized logging for JARVIS."""
import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(f"jarvis.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler
    fh = logging.FileHandler(LOG_DIR / "jarvis.log")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
