"""Точка входа сервиса мониторинга HTTP-маршрутов."""
from __future__ import annotations

import argparse
import logging
import time
from threading import Event

import init
from monitoring import MonitoringConfig, ResultWriter, load_config
from threads import build_monitors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTP route monitoring for Zabbix collectors")
    parser.add_argument(
        "--config",
        default="config/routes.yaml",
        help="Path to YAML/JSON file with route definitions (default: config/routes.yaml)",
    )
    parser.add_argument(
        "--results-file",
        default="monitoring_results.json",
        help="Where to store the latest probe results for Zabbix",
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

    writer = ResultWriter(args.results_file)
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
