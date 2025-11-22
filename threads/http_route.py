"""Поток мониторинга HTTP-маршрута."""
from __future__ import annotations
import json
from contextlib import ExitStack
import time
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from threading import Event
from typing import Any, Dict, Mapping, Optional
import zipfile

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
                data = self.config.data
                json_payload = self.config.json_body
                params = self._copy_mapping(self.config.params)
                headers = self._copy_mapping(self.config.headers)

                if json_payload is not None and self.config.json_query_param:
                    params = params or {}
                    params[self.config.json_query_param] = self._encode_json_field(
                        json_payload, encoding=self.config.encoding_json
                    )
                    json_payload = None

                if files and json_payload is not None:
                    files = self._inject_json_part(files, json_payload)
                    json_payload = None

                if files and headers:
                    # Не даём пользователю фиксировать Content-Type, чтобы requests проставил boundary для multipart
                    headers = self._drop_content_type(headers)

                response = self.session.request(
                    method=self.config.method,
                    url=self.config.url,
                    headers=self._empty_to_none(headers),
                    params=self._empty_to_none(params),
                    data=data,
                    json=json_payload,
                    files=files,
                    auth=self._basic_auth(),
                    timeout=self.config.timeout,
                    allow_redirects=self.config.allow_redirects,
                    verify=self._verify_option(),
                )
        except (requests.RequestException, OSError, ValueError) as exc:
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

        file_path = path
        filename = path.name
        content_type = upload.content_type or "application/octet-stream"

        should_zip = False
        if path.is_dir():
            if not upload.zip_enabled:
                raise ValueError(
                    f"Для отправки директории {path} нужно включить zip_enabled: true в конфиге file."
                )
            should_zip = True
        elif upload.zip_enabled and path.suffix.lower() != ".zip":
            should_zip = True

        if should_zip:
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            base_name = path.name if path.is_dir() else path.stem
            archive_path = Path(tmp_dir) / f"{base_name}.zip"
            self._build_zip(path, archive_path, target_encoding=self.config.encoding_file)
            file_path = archive_path
            filename = archive_path.name
            content_type = "application/zip"

        file_obj = stack.enter_context(open(file_path, "rb"))
        return {
            upload.field_name: (
                filename,
                file_obj,
                content_type,
            )
        }

    def _inject_json_part(self, files: Dict[str, Any], payload: Any) -> Dict[str, Any]:
        files_copy = dict(files)
        field_name = self.config.multipart_json_field or "json"

        if field_name in files_copy:
            self.logger.debug("Поле %s уже существует среди files и будет перезаписано JSON-частью.", field_name)

        effective_encoding = self.config.encoding_json or "utf-8"
        encoded_json = self._encode_json_field(payload, encoding=effective_encoding, as_bytes=True)
        content_type = f"application/json; charset={effective_encoding}"
        files_copy[field_name] = (
            None,
            encoded_json,
            content_type,
        )
        return files_copy

    @staticmethod
    def _encode_json_field(payload: Any, encoding: Optional[str] = None, as_bytes: bool = False) -> Any:
        if isinstance(payload, bytes):
            if not as_bytes and encoding:
                try:
                    return payload.decode(encoding)
                except (LookupError, UnicodeDecodeError):
                    return payload.decode(errors="replace")
            return payload
        if isinstance(payload, str):
            payload_str = payload
        else:
            try:
                payload_str = json.dumps(payload, ensure_ascii=False)
            except TypeError:
                payload_str = str(payload)

        if as_bytes:
            target_encoding = encoding or "utf-8"
            try:
                return payload_str.encode(target_encoding)
            except LookupError:
                return payload_str.encode()
        return payload_str

    @staticmethod
    def _write_entry_with_reencode(
        archive: zipfile.ZipFile, path: Path, arcname: str, target_encoding: Optional[str]
    ) -> None:
        encoding = target_encoding or "utf-8"
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise OSError(f"Не удалось прочитать файл для архивации: {path}") from exc

        data = HttpRouteMonitor._reencode_bytes(raw, encoding)
        archive.writestr(arcname, data)

    @staticmethod
    def _reencode_bytes(raw: bytes, target_encoding: str) -> bytes:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw  # не можем декодировать — добавляем как есть
        try:
            return text.encode(target_encoding)
        except (LookupError, UnicodeEncodeError):
            return raw

    @staticmethod
    def _build_zip(source: Path, target: Path, target_encoding: Optional[str]) -> None:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if source.is_file():
                arcname = source.name
                HttpRouteMonitor._write_entry_with_reencode(archive, source, arcname, target_encoding)
                return

            # Добавляем саму папку и все вложения, сохраняя относительные пути.
            root_arcname = f"{source.name}/"
            archive.writestr(root_arcname, b"")
            for entry in sorted(source.rglob("*")):
                relative = entry.relative_to(source.parent).as_posix()
                if entry.is_dir():
                    archive.writestr(f"{relative}/", b"")
                    continue
                HttpRouteMonitor._write_entry_with_reencode(archive, entry, relative, target_encoding)

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

    @staticmethod
    def _copy_mapping(value: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        return dict(value)

    def _drop_content_type(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(headers)
        removed = False
        for key in list(cleaned.keys()):
            if key.lower() == "content-type":
                cleaned.pop(key, None)
                removed = True
        if removed:
            self.logger.debug("Удалён заголовок Content-Type: requests сам установит boundary для multipart.")
        return cleaned

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
