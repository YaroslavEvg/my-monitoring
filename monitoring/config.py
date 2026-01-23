"""Загрузчик конфигурации маршрутов мониторинга."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - защитный блок
    raise RuntimeError(
        "Библиотека PyYAML не установлена. Выполните `pip install -r requirements.txt` или "
        "`pip install PyYAML` и повторите запуск."
    ) from exc

from .env import build_env_map
from .types import HttpRouteConfig

SUPPORTED_EXTENSIONS = {".yaml", ".yml", ".json"}


@dataclass
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
        raise FileNotFoundError(f"Config file or directory not found: {path}")

    routes: List[HttpRouteConfig] = []

    if path.is_file():
        routes.extend(_load_routes_from_file(path, source_label=path.name))
    else:
        config_files = sorted(_iter_config_files(path))
        if not config_files:
            raise ValueError(f"Directory {path} does not contain config files (*.yaml, *.yml, *.json)")
        for file_path in config_files:
            relative = file_path.relative_to(path).as_posix()
            routes.extend(_load_routes_from_file(file_path, source_label=relative))

    if not routes:
        raise ValueError("Config does not contain any routes")

    return MonitoringConfig(routes=routes)


def _iter_config_files(root: Path) -> Iterable[Path]:
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield candidate


def _load_routes_from_file(path: Path, source_label: str) -> List[HttpRouteConfig]:
    raw_config = _read_file(path)
    if "routes" not in raw_config:
        raise ValueError(f"Config file {path} must contain a 'routes' section")
    env_map = build_env_map(raw_config.get("env"))
    base_dir = path.parent
    return [
        HttpRouteConfig.from_dict(entry, source_path=source_label, base_dir=base_dir, env_map=env_map)
        for entry in raw_config["routes"]
    ]
