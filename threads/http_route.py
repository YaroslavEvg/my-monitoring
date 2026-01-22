"""Поток мониторинга HTTP-маршрута."""
from __future__ import annotations
import json
import re
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
_MISSING = object()
_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


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
        payload = self._execute_request_chain(self.config, None)
        self.writer.write_result(self.config, payload)

    def _execute_request_chain(self, config: HttpRouteConfig, context: Optional[Any]) -> Dict[str, Any]:
        results, total_time = self._collect_chain_results(config, context)
        selected = self._select_chain_result(results)
        if not selected:
            return {}
        payload = dict(selected)
        payload["response_time_ms"] = round(total_time, 2)
        return payload

    def _collect_chain_results(
        self, config: HttpRouteConfig, context: Optional[Any], parent_children_delay: float = 0.0
    ) -> tuple[list[Dict[str, Any]], float]:
        effective_delay = config.delay_before if config.delay_before is not None else parent_children_delay
        result, response_json, has_response = self._execute_request(config, context, pre_delay=effective_delay)
        results: list[Dict[str, Any]] = [result]
        total_time = float(result.get("response_time_ms") or 0)

        if config.children:
            if not has_response:
                self.logger.debug("Дочерние запросы для %s пропущены: отсутствует ответ.", config.name)
            else:
                for child in config.children:
                    if not child.enabled:
                        continue
                    child_results, child_time = self._collect_chain_results(
                        child, response_json, parent_children_delay=config.children_delay
                    )
                    results.extend(child_results)
                    total_time += child_time

        return results, total_time

    @staticmethod
    def _select_chain_result(results: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for result in results:
            if not result.get("ok", False):
                return result
        if results:
            return results[-1]
        return None

    def _execute_request(
        self, config: HttpRouteConfig, context: Optional[Any], pre_delay: float = 0.0
    ) -> tuple[Dict[str, Any], Optional[Any], bool]:
        wait_for = config.wait_for
        attempts = wait_for.attempts if wait_for else 1
        total_time = 0.0
        if pre_delay:
            self._sleep(pre_delay)
            total_time += pre_delay * 1000

        last_result: Optional[Dict[str, Any]] = None
        last_json: Optional[Any] = None
        has_response = False
        wait_failed = False

        for attempt in range(attempts):
            result, response_json, has_response = self._execute_request_once(config, context)
            last_result = result
            last_json = response_json
            total_time += float(result.get("response_time_ms") or 0)

            if not wait_for:
                break

            if has_response and response_json is not None:
                extracted = self._extract_json_path(response_json, wait_for.path)
                if extracted is not _MISSING:
                    wait_failed = False
                    break
            wait_failed = True
            if attempt < attempts - 1:
                self._sleep(wait_for.delay)
                total_time += wait_for.delay * 1000

        if last_result is None:
            return {}, None, False

        if wait_for:
            last_result["response_time_ms"] = round(total_time, 2)
            if wait_failed:
                if last_result.get("ok", True):
                    last_result["ok"] = False
                if not last_result.get("error"):
                    last_result["error"] = (
                        f"Не найден путь {wait_for.path} после {attempts} попыток"
                    )
        return last_result, last_json, has_response

    def _execute_request_once(
        self, config: HttpRouteConfig, context: Optional[Any]
    ) -> tuple[Dict[str, Any], Optional[Any], bool]:
        timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        start = time.perf_counter()
        error_payload: Optional[str] = None
        response: Optional[requests.Response] = None
        response_json: Optional[Any] = None
        url: Any = config.url

        try:
            with ExitStack() as stack:
                files = self._prepare_files(stack, config)
                extra_json_parts = self._prepare_multipart_json_fields(config, context)
                if extra_json_parts:
                    files = files or {}
                    for field_name, part in extra_json_parts.items():
                        if field_name in files:
                            self.logger.debug(
                                "Поле %s уже существует среди files и будет перезаписано JSON-частью.", field_name
                            )
                        files[field_name] = part
                data = self._resolve_value(config.data, context)
                json_payload = self._resolve_value(config.json_body, context)
                params = self._resolve_mapping(config.params, context)
                headers = self._resolve_mapping(config.headers, context)
                url = self._resolve_text(config.url, context)
                if not isinstance(url, str):
                    url = str(url)

                if json_payload is not None and config.json_query_param:
                    params = params or {}
                    params[config.json_query_param] = self._encode_json_field(
                        json_payload, encoding=config.encoding_json
                    )
                    json_payload = None

                if files and json_payload is not None:
                    files = self._inject_json_part(files, json_payload, config)
                    json_payload = None

                if files and headers:
                    # Не даём пользователю фиксировать Content-Type, чтобы requests проставил boundary для multipart
                    headers = self._drop_content_type(headers)

                response = self.session.request(
                    method=config.method,
                    url=url,
                    headers=self._empty_to_none(headers),
                    params=self._empty_to_none(params),
                    data=data,
                    json=json_payload,
                    files=files,
                    auth=self._basic_auth(config),
                    timeout=config.timeout,
                    allow_redirects=config.allow_redirects,
                    verify=self._verify_option(config),
                )
        except (requests.RequestException, OSError, ValueError) as exc:
            error_payload = str(exc)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

        result: Dict[str, Any] = {
            "name": config.name,
            "url": url,
            "method": config.method,
            "timestamp": timestamp,
            "response_time_ms": duration_ms,
            "tags": config.tags,
        }

        if response is not None:
            response_json = self._safe_json(response)
            body, truncated = self._safe_body(response, config)
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

        return result, response_json, response is not None

    def _prepare_files(self, stack: ExitStack, config: HttpRouteConfig) -> Optional[Dict[str, Any]]:
        if not config.file_upload:
            return None

        upload = config.file_upload
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
            self._build_zip(path, archive_path, target_encoding=config.encoding_file)
            file_path = archive_path
            filename = archive_path.name
            content_type = "application/zip"
        if not should_zip and self._is_text_content_type(content_type):
            content_type = self._ensure_text_charset(content_type, config.encoding_file)

        file_obj = stack.enter_context(open(file_path, "rb"))
        return {
            upload.field_name: (
                filename,
                file_obj,
                content_type,
            )
        }

    def _inject_json_part(self, files: Dict[str, Any], payload: Any, config: HttpRouteConfig) -> Dict[str, Any]:
        files_copy = dict(files)
        field_name = config.multipart_json_field or "json"

        if field_name in files_copy:
            self.logger.debug("Поле %s уже существует среди files и будет перезаписано JSON-частью.", field_name)

        files_copy[field_name] = self._build_json_part(payload, config.encoding_json)
        return files_copy

    def _prepare_multipart_json_fields(
        self, config: HttpRouteConfig, context: Optional[Any]
    ) -> Dict[str, Any]:
        if not config.multipart_json_fields:
            return {}
        parts: Dict[str, Any] = {}
        for field in config.multipart_json_fields:
            payload = self._resolve_value(field.payload, context)
            encoding = field.encoding or config.encoding_json
            parts[field.field_name] = self._build_json_part(payload, encoding)
        return parts

    def _build_json_part(self, payload: Any, encoding: Optional[str]) -> tuple[None, Any, str]:
        effective_encoding = encoding or "utf-8"
        encoded_json = self._encode_json_field(payload, encoding=effective_encoding, as_bytes=True)
        content_type = f"application/json; charset={effective_encoding}"
        return (
            None,
            encoded_json,
            content_type,
        )

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
    def _is_text_content_type(content_type: str) -> bool:
        return content_type.strip().lower().startswith("text/")

    @staticmethod
    def _ensure_text_charset(content_type: str, encoding: Optional[str]) -> str:
        if "charset=" in content_type.lower():
            return content_type
        effective = encoding or "utf-8"
        return f"{content_type}; charset={effective}"

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

    def _safe_body(self, response: requests.Response, config: HttpRouteConfig) -> tuple[TextResponse, bool]:
        try:
            body = response.text
        except UnicodeDecodeError:
            body = "<binary content>"
        if body is None:
            return None, False
        max_chars = max(config.body_max_chars, 1)
        if len(body) <= max_chars:
            return body, False
        return f"{body[:max_chars]}...", True

    @staticmethod
    def _safe_json(response: requests.Response) -> Optional[Any]:
        try:
            return response.json()
        except ValueError:
            return None

    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self.stop_event.wait(seconds)

    @staticmethod
    def _empty_to_none(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        return value

    def _resolve_mapping(self, value: Optional[Mapping[str, Any]], context: Optional[Any]) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        return {key: self._resolve_value(val, context) for key, val in value.items()}

    def _resolve_value(self, value: Any, context: Optional[Any]) -> Any:
        if context is None:
            return value
        if isinstance(value, dict):
            return {key: self._resolve_value(val, context) for key, val in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, context) for item in value]
        if isinstance(value, tuple):
            return tuple(self._resolve_value(item, context) for item in value)
        if isinstance(value, str):
            return self._resolve_text(value, context)
        return value

    def _resolve_text(self, value: str, context: Optional[Any]) -> Any:
        if context is None:
            return value
        raw = value.strip()
        if raw == "$" or raw.startswith("$."):
            extracted = self._extract_json_path(context, raw)
            if extracted is not _MISSING:
                return extracted
        if "{{" not in value:
            return value

        def replacer(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if not expr.startswith("$"):
                return match.group(0)
            extracted = self._extract_json_path(context, expr)
            if extracted is _MISSING:
                self.logger.debug("Не удалось извлечь значение по пути %s", expr)
                return match.group(0)
            if isinstance(extracted, (dict, list)):
                try:
                    return json.dumps(extracted, ensure_ascii=False)
                except TypeError:
                    return str(extracted)
            return str(extracted)

        return _TEMPLATE_RE.sub(replacer, value)

    @staticmethod
    def _extract_json_path(payload: Any, path: str) -> Any:
        if payload is None:
            return _MISSING
        raw = path.strip()
        if raw == "$":
            return payload
        if not raw.startswith("$."):
            return _MISSING
        tokens = HttpRouteMonitor._tokenize_path(raw[2:])
        return HttpRouteMonitor._extract_tokens(payload, tokens)

    @staticmethod
    def _tokenize_path(path: str) -> list[Any]:
        tokens: list[Any] = []
        for segment in path.split("."):
            if not segment:
                continue
            tokens.extend(HttpRouteMonitor._tokenize_segment(segment))
        return tokens

    @staticmethod
    def _tokenize_segment(segment: str) -> list[Any]:
        tokens: list[Any] = []
        idx = segment.find("[")
        if idx == -1:
            tokens.append(segment)
            return tokens

        base = segment[:idx]
        if base:
            tokens.append(base)

        cursor = idx
        while cursor < len(segment) and segment[cursor] == "[":
            end = segment.find("]", cursor + 1)
            if end == -1:
                break
            content = segment[cursor + 1 : end].strip()
            token = HttpRouteMonitor._parse_bracket_token(content)
            if token is not None:
                tokens.append(token)
            cursor = end + 1
        return tokens

    @staticmethod
    def _parse_bracket_token(content: str) -> Optional[Any]:
        if not content:
            return None
        if content.isdigit():
            return int(content)
        if "==" in content:
            left, right = content.split("==", 1)
            return ("filter", left.strip(), HttpRouteMonitor._parse_literal(right.strip()))
        if "=" in content:
            left, right = content.split("=", 1)
            return ("filter", left.strip(), HttpRouteMonitor._parse_literal(right.strip()))
        return content

    @staticmethod
    def _parse_literal(raw: str) -> Any:
        if not raw:
            return ""
        if raw[0] in {"'", '"'} and raw[-1] == raw[0]:
            quote = raw[0]
            inner = raw[1:-1]
            inner = inner.replace("\\\\", "\\")
            inner = inner.replace(f"\\{quote}", quote)
            return inner
        lowered = raw.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered == "null":
            return None
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw

    @staticmethod
    def _extract_tokens(payload: Any, tokens: list[Any]) -> Any:
        current = payload
        for token in tokens:
            if isinstance(token, int):
                if not isinstance(current, (list, tuple)) or token >= len(current):
                    return _MISSING
                current = current[token]
                continue
            if isinstance(token, tuple) and token and token[0] == "filter":
                current = HttpRouteMonitor._select_from_list(current, token)
                if current is _MISSING:
                    return _MISSING
                continue
            if not isinstance(current, Mapping) or token not in current:
                return _MISSING
            current = current[token]
        return current

    @staticmethod
    def _extract_relative(payload: Any, path: str) -> Any:
        raw = path.strip()
        if raw in {"", "$"}:
            return payload
        if raw.startswith("$."):
            raw = raw[2:]
        tokens = HttpRouteMonitor._tokenize_path(raw)
        return HttpRouteMonitor._extract_tokens(payload, tokens)

    @staticmethod
    def _select_from_list(current: Any, token: tuple[str, str, Any]) -> Any:
        if not isinstance(current, (list, tuple)):
            return _MISSING
        _, key_path, expected = token
        for item in current:
            value = HttpRouteMonitor._extract_relative(item, key_path)
            if value is _MISSING:
                continue
            if value == expected:
                return item
        return _MISSING

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

    def _basic_auth(self, config: HttpRouteConfig) -> Optional[HTTPBasicAuth]:
        if not config.basic_auth:
            return None
        creds = config.basic_auth
        return HTTPBasicAuth(creds.username, creds.password)

    def _verify_option(self, config: HttpRouteConfig) -> Any:
        if not config.ca_bundle:
            return config.verify_ssl

        ca_path = Path(config.ca_bundle).expanduser()
        if not ca_path.exists():
            self.logger.warning(
                "Файл пользовательского сертификата %s не найден, fallback к verify=%s",
                ca_path,
                config.verify_ssl,
            )
            return config.verify_ssl
        return str(ca_path)
