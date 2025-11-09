"""Утилиты логирования для сервиса мониторинга."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional, Union

_LOGGER_INITIALIZED = False


def _to_numeric_level(level: Union[str, int]) -> int:
    if isinstance(level, int):
        return level
    numeric_level = logging.getLevelName(level.upper())
    if isinstance(numeric_level, int):
        return numeric_level
    raise ValueError(f"Unsupported log level: {level}")


def init_logging(level: Union[str, int] = "INFO", log_files: Optional[Iterable[str]] = None) -> None:
    """Единоразово настраивает глобальное логирование."""
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return

    handlers = [logging.StreamHandler()]
    for file_path in log_files or []:
        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    logging.basicConfig(
        level=_to_numeric_level(level),
        format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    _LOGGER_INITIALIZED = True
