"""Поток мониторинга HTTP-маршрута."""
from __future__ import annotations

import json
from contextlib import ExitStack
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from monitoring.persistence import ResultWriter
from monitoring.types import HttpRouteConfig
from threads.base import BaseMonitorThread

TextResponse = Optional[str]


class HttpRouteMonitor(BaseMonitorThread):
    def __init__(
        self, config: HttpRouteConfig, writer: ResultWriter, stop_event: Event, one_shot: bool = False
    ) -> None:
        super().__init__(name=config.name, interval=config.interval, stop_event=stop_event, one_shot=one_shot)
        self.config = config
        self.writer = writer
        self.session = requests.Session()

    def run(self) -> None:
        try:
            super().run()
        finally:
            self.session.close()

    def run_once(self) -> None:
        payload = self._execute_request()
        self.writer.write_result(self.config, payload)

    def _execute_request(self) -> Dict[str, Any]:
        timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        start = time.perf_counter()
        error_payload: Optional[str] = None
        response: Optional[requests.Response] = None

        try:
            with ExitStack() as stack:
                files = self._prepare_files(stack)
                data, json_payload = self._prepare_bodies(files)
                response = self.session.request(
                    method=self.config.method,
                    url=self.config.url,
                    headers=self._empty_to_none(self.config.headers),
                    params=self._empty_to_none(self.config.params),
                    data=data,
                    json=json_payload,
                    files=files,
                    auth=self._basic_auth(),
                    timeout=self.config.timeout,
                    allow_redirects=self.config.allow_redirects,
                    verify=self._verify_option(),
                )
        except (requests.RequestException, OSError) as exc:
            error_payload = str(exc)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

        result: Dict[str, Any] = {
            "name": self.config.name,
            "url": self.config.url,
            "method": self.config.method,
            "timestamp": timestamp,
            "response_time_ms": duration_ms,
            "tags": self.config.tags,
        }

        if response is not None:
            body, truncated = self._safe_body(response)
            result.update(
                {
                    "status_code": response.status_code,
                    "reason": response.reason,
                    "ok": response.ok,
                    "body_excerpt": body,
                    "body_truncated": truncated,
                    "error": None,
                }
            )
        else:
            result.update(
                {
                    "status_code": None,
                    "reason": None,
                    "ok": False,
                    "body_excerpt": None,
                    "body_truncated": False,
                    "error": error_payload,
                }
            )

        return result

    def _prepare_files(self, stack: ExitStack) -> Optional[Dict[str, Any]]:
        if not self.config.file_upload:
            return None

        upload = self.config.file_upload
        path = upload.resolved_path()

        file_obj = stack.enter_context(open(path, "rb"))
        return {
            upload.field_name: (
                path.name,
                file_obj,
                upload.content_type or "application/octet-stream",
            )
        }

    def _prepare_bodies(self, files: Optional[Dict[str, Any]]) -> tuple[Optional[Any], Optional[Any]]:
        data = self.config.data
        json_payload = self.config.json_body

        if not files or json_payload is None:
            return data, json_payload

        field_name = self.config.multipart_json_field or "json"
        encoded_json = self._encode_json_field(json_payload)

        if data is None:
            data = {field_name: encoded_json}
            return data, None

        if isinstance(data, dict):
            data = dict(data)
            if field_name in data:
                self.logger.debug(
                    "Поле %s уже присутствует в data, перезаписываем JSON-значением для multipart.",
                    field_name,
                )
            data[field_name] = encoded_json
            return data, None

        self.logger.warning(
            "Не удалось объединить JSON-тело с multipart-формой: data имеет тип %s", type(data).__name__
        )
        return data, json_payload

    @staticmethod
    def _encode_json_field(payload: Any) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False)
        except TypeError:
            return str(payload)

    def _safe_body(self, response: requests.Response) -> tuple[TextResponse, bool]:
        try:
            body = response.text
        except UnicodeDecodeError:
            body = "<binary content>"
        if body is None:
            return None, False
        max_chars = max(self.config.body_max_chars, 1)
        if len(body) <= max_chars:
            return body, False
        return f"{body[:max_chars]}...", True

    @staticmethod
    def _empty_to_none(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        return value

    def _basic_auth(self) -> Optional[HTTPBasicAuth]:
        if not self.config.basic_auth:
            return None
        creds = self.config.basic_auth
        return HTTPBasicAuth(creds.username, creds.password)

    def _verify_option(self) -> Any:
        if not self.config.ca_bundle:
            return self.config.verify_ssl

        ca_path = Path(self.config.ca_bundle).expanduser()
        if not ca_path.exists():
            self.logger.warning(
                "Файл пользовательского сертификата %s не найден, fallback к verify=%s",
                ca_path,
                self.config.verify_ssl,
            )
            return self.config.verify_ssl
        return str(ca_path)
