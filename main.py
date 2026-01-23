"""Точка входа сервиса мониторинга HTTP-маршрутов."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from threading import Event
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import init
from monitoring.config import MonitoringConfig, load_config
from monitoring.env import apply_env
from monitoring.persistence import ResultWriter
from threads.factory import build_monitors

DEFAULT_TZ = "Europe/Moscow"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTP route monitoring for Zabbix collectors")
    parser.add_argument(
        "--config",
        default="config/routes",
        help="Path to a YAML/JSON file or directory with route definitions (default: config/routes)",
    )
    parser.add_argument(
        "--results-path",
        "--results-file",
        dest="results_path",
        default="monitoring_results.json",
        help="Path to a JSON file or directory where probe results will be stored",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Path to .env file with KEY=VALUE entries (can be repeated)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, etc.)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional log file path",
    )
    parser.add_argument(
        "--one-shot",
        action="store_true",
        help="Run every monitor once and exit (useful for ad-hoc checks)",
    )
    return parser.parse_args()


def _load_env_files(paths: list[str]) -> None:
    if not paths:
        return
    env_map = dict(os.environ)
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f".env file not found: {path}")
        file_env = _parse_env_file(path, env_map)
        env_map.update(file_env)
    os.environ.update({key: str(value) for key, value in env_map.items()})


def _parse_env_file(path: Path, base_env: dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        item = _parse_env_line(line)
        if not item:
            continue
        key, raw_value = item
        resolved_value = apply_env(raw_value, {**base_env, **parsed})
        parsed[key] = str(resolved_value)
    return parsed


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.startswith("export "):
        raw = raw[7:].strip()
    if "=" not in raw:
        return None
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, _parse_env_value(value)


def _parse_env_value(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if raw[0] in {"'", '"'}:
        quote = raw[0]
        buf = []
        escape = False
        for ch in raw[1:]:
            if escape:
                buf.append(ch)
                escape = False
                continue
            if quote == '"' and ch == "\\":
                escape = True
                continue
            if ch == quote:
                break
            buf.append(ch)
        return "".join(buf)
    buf = []
    for idx, ch in enumerate(raw):
        if ch == "#" and (idx == 0 or raw[idx - 1].isspace()):
            break
        buf.append(ch)
    return "".join(buf).strip()


def configure_timezone(default_tz: str = DEFAULT_TZ) -> str:
    """Настраивает часовой пояс: TZ из окружения или дефолт Europe/Moscow."""
    tz_value = os.environ.get("TZ", default_tz)
    os.environ["TZ"] = tz_value
    if hasattr(time, "tzset"):
        try:
            time.tzset()
        except Exception:  # noqa: BLE001
            pass
    return tz_value


def _wait_for(monitors, stop_event: Event, one_shot: bool) -> None:
    try:
        while True:
            alive = any(m.is_alive() for m in monitors)
            if not alive:
                break
            time.sleep(1)
            if one_shot and not alive:
                break
    except KeyboardInterrupt:
        logging.info("Received interrupt, stopping monitors...")
        stop_event.set()
    finally:
        for monitor in monitors:
            monitor.join(timeout=5)


def main() -> int:
    args = parse_args()
    try:
        _load_env_files(args.env_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load .env files: {exc}", file=sys.stderr)
        return 1
    configure_timezone()
    log_files = [args.log_file] if args.log_file else None
    init.init_logging(args.log_level, log_files=log_files)

    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to load config %s: %s", args.config, exc)
        return 1

    enabled_routes = config.enabled_routes
    if not enabled_routes:
        logging.warning("No enabled routes configured. Nothing to monitor.")
        return 0

    writer = ResultWriter(args.results_path)
    stop_event = Event()

    try:
        monitors = build_monitors(enabled_routes, writer, stop_event, one_shot=args.one_shot)
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to initialize monitors: %s", exc)
        return 1

    for monitor in monitors:
        monitor.start()
        logging.info(
            "Started monitor %s %s %s interval=%ss",
            monitor.config.name,
            monitor.config.method,
            monitor.config.url,
            monitor.config.interval,
        )

    _wait_for(monitors, stop_event, args.one_shot)
    logging.info("Monitoring stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
