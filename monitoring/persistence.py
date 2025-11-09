"""Потокобезопасная запись результатов мониторинга."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict


class ResultWriter:
    """Хранит последние результаты проверок для чтения агентом Zabbix."""

    def __init__(self, output_path: str, schema_version: int = 1) -> None:
        self.path = Path(output_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.schema_version = schema_version

    def write_result(self, route_name: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            state = self._safe_read()
            state.setdefault("routes", {})
            state["routes"][route_name] = payload
            state["last_updated"] = payload.get("timestamp")
            state["schema_version"] = self.schema_version
            self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _safe_read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"routes": {}, "schema_version": self.schema_version}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"routes": {}, "schema_version": self.schema_version}
