"""Загрузчик конфигурации маршрутов мониторинга."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

import yaml

from .types import HttpRouteConfig


@dataclass(slots=True)
class MonitoringConfig:
    routes: List[HttpRouteConfig]

    @property
    def enabled_routes(self) -> List[HttpRouteConfig]:
        return [route for route in self.routes if route.enabled]


def _read_file(path: Path) -> Any:
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(content) or {}
    if suffix == ".json":
        return json.loads(content or "{}")
    raise ValueError(f"Unsupported config format: {suffix}")


def load_config(config_path: str) -> MonitoringConfig:
    path = Path(config_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw_config = _read_file(path)
    if "routes" not in raw_config:
        raise ValueError("Config must contain a 'routes' section")

    routes = [HttpRouteConfig.from_dict(entry) for entry in raw_config["routes"]]

    if not routes:
        raise ValueError("Config file does not contain any routes")

    return MonitoringConfig(routes=routes)
