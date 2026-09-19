from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "runner"
_CONFIGURED = False


def configure(log_dir: Path, level: str = "INFO") -> logging.Logger:
    global _CONFIGURED

    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_dir / "runner.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _CONFIGURED = True
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def configure_from_env(default_root: Optional[Path] = None) -> logging.Logger:
    root = Path(os.environ.get("RUNNER_ROOT", default_root or Path.cwd()))
    log_dir = Path(os.environ.get("RUNNER_LOG_DIR", root / "logs"))
    level = os.environ.get("RUNNER_LOG_LEVEL", "INFO")
    return configure(log_dir, level)
