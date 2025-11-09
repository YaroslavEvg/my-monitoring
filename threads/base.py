"""Базовый класс для потоков мониторинга."""
from __future__ import annotations

import logging
import threading
from typing import Optional


class BaseMonitorThread(threading.Thread):
    """Простой поток, который запускает `run_once` по расписанию."""

    def __init__(self, name: str, interval: float, stop_event: threading.Event, one_shot: bool = False) -> None:
        super().__init__(name=f"monitor-{name}", daemon=True)
        self.interval = max(interval, 1.0)
        self.stop_event = stop_event
        self.one_shot = one_shot
        self.logger = logging.getLogger(name)

    def run_once(self) -> None:
        raise NotImplementedError

    def run(self) -> None:  # pragma: no cover - threading loop is simple
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception:  # noqa: BLE001
                self.logger.exception("Необработанная ошибка в потоке мониторинга")
            if self.one_shot:
                break
            self.stop_event.wait(self.interval)
