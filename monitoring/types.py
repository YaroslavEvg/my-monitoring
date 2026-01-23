"""Dataclass-описания конфигурации мониторинга."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .env import apply_env, build_env_map


@dataclass
class FileUploadConfig:
    """Параметры отправки файла в HTTP-запросе."""

    path: str
    field_name: str = "file"
    content_type: Optional[str] = None
    zip_enabled: bool = False

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()


@dataclass
class MultipartJsonField:
    """JSON-часть внутри multipart/form-data."""

    field_name: str
    payload: Any
    encoding: Optional[str] = None


@dataclass
class WaitForConfig:
    """Ожидание появления поля в JSON-ответе."""

    path: str
    attempts: int = 1
    delay: float = 0.0


@dataclass
class BasicAuthConfig:
    """Пара логина/пароля для базовой авторизации."""

    username: str
    password: str


@dataclass
class HttpRouteConfig:
    """Конфигурация одного HTTP-монитора."""

    name: str
    url: str
    method: str = "GET"
    interval: float = 60.0
    timeout: float = 10.0
    headers: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)
    data: Optional[Any] = None
    json_body: Optional[Any] = None
    allow_redirects: bool = True
    verify_ssl: bool = True
    ca_bundle: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    body_max_chars: int = 2048
    file_upload: Optional[FileUploadConfig] = None
    basic_auth: Optional[BasicAuthConfig] = None
    multipart_json_field: Optional[str] = None
    multipart_json_fields: List[MultipartJsonField] = field(default_factory=list)
    json_query_param: Optional[str] = None
    encoding_file: str = "utf-8"
    encoding_json: str = "utf-8"
    delay_before: Optional[float] = None
    children_delay: float = 0.0
    wait_for: Optional[WaitForConfig] = None
    tags: List[str] = field(default_factory=list)
    monitor_type: str = "http"
    source_path: Optional[str] = None
    children: List["HttpRouteConfig"] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, Any],
        source_path: Optional[str] = None,
        base_dir: Optional[Path] = None,
        env_map: Optional[Mapping[str, Any]] = None,
    ) -> "HttpRouteConfig":
        effective_env = env_map
        if isinstance(raw, Mapping) and raw.get("env") is not None:
            effective_env = build_env_map(raw.get("env"), base_env=env_map)
        children_raw = raw.get("children") or []
        if children_raw and not isinstance(children_raw, list):
            raise ValueError("Поле children должно быть списком маршрутов")
        raw_local = dict(raw)
        raw_local.pop("children", None)
        if effective_env:
            raw_local = apply_env(raw_local, effective_env)
        file_config = raw_local.get("file") or raw_local.get("file_upload")
        file_upload = FileUploadConfig(**file_config) if file_config else None
        auth_config = raw_local.get("basic_auth") or raw_local.get("auth")
        basic_auth = BasicAuthConfig(**auth_config) if auth_config else None
        interval = max(float(raw_local.get("interval", 60)), 1.0)
        timeout = max(float(raw_local.get("timeout", 10)), 1.0)
        body_limit = int(raw_local.get("max_response_chars", raw_local.get("body_max_chars", 2048)))
        json_payload = cls._resolve_json_payload(raw_local.get("json"), base_dir, effective_env)

        # multipart_json_fields допускает краткую запись в виде словаря.
        multipart_json_fields = cls._parse_multipart_json_fields(
            raw_local.get("multipart_json_fields") or raw_local.get("multipart_json"),
            base_dir,
            effective_env,
        )
        # wait_for можно задавать строкой или объектом.
        wait_for = cls._parse_wait_for(raw_local.get("wait_for"))
        delay_before = cls._parse_delay(raw_local.get("delay_before") or raw_local.get("pre_delay"))
        children_delay = cls._parse_delay(raw_local.get("children_delay") or raw_local.get("children_timeout")) or 0.0
        children = [
            cls.from_dict(entry, source_path=source_path, base_dir=base_dir, env_map=effective_env)
            for entry in children_raw
        ]

        return cls(
            name=raw_local["name"],
            url=raw_local["url"],
            method=str(raw_local.get("method", "GET")).upper(),
            interval=interval,
            timeout=timeout,
            headers=dict(raw_local.get("headers", {})),
            params=dict(raw_local.get("params", {})),
            data=raw_local.get("data") or raw_local.get("body"),
            json_body=json_payload,
            allow_redirects=raw_local.get("allow_redirects", True),
            verify_ssl=raw_local.get("verify_ssl", True),
            ca_bundle=raw_local.get("ca_bundle") or raw_local.get("ca_cert") or raw_local.get("verify_path"),
            description=raw_local.get("description"),
            enabled=raw_local.get("enabled", True),
            body_max_chars=body_limit,
            file_upload=file_upload,
            basic_auth=basic_auth,
            multipart_json_field=raw_local.get("multipart_json_field") or raw_local.get("json_field"),
            multipart_json_fields=multipart_json_fields,
            json_query_param=raw_local.get("json_query_param") or raw_local.get("json_param"),
            encoding_file=raw_local.get("encoding_file") or raw_local.get("encondig_file") or "utf-8",
            encoding_json=raw_local.get("encoding_json") or raw_local.get("encondig_json") or "utf-8",
            delay_before=delay_before,
            children_delay=children_delay,
            wait_for=wait_for,
            tags=list(raw_local.get("tags", [])),
            monitor_type=raw_local.get("type", "http").lower(),
            source_path=source_path,
            children=children,
        )

    @staticmethod
    def _resolve_json_payload(
        payload: Any, base_dir: Optional[Path], env_map: Optional[Mapping[str, Any]]
    ) -> Any:
        if env_map:
            payload = apply_env(payload, env_map)
        if not isinstance(payload, str):
            return payload

        raw_value = payload.strip()
        if not raw_value:
            return payload

        candidates = []
        path_obj = Path(raw_value)
        if path_obj.is_absolute():
            candidates.append(path_obj)
        else:
            candidates.append(path_obj)
            if base_dir:
                candidates.append((base_dir / raw_value).resolve())

        for candidate in candidates:
            file_path = candidate.expanduser()
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parsed = json.loads(content or "null")
                    return apply_env(parsed, env_map) if env_map else parsed
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON content in {file_path}: {exc}") from exc

        return payload

    @classmethod
    def _parse_multipart_json_fields(
        cls, raw_value: Any, base_dir: Optional[Path], env_map: Optional[Mapping[str, Any]]
    ) -> List[MultipartJsonField]:
        if not raw_value:
            return []
        if isinstance(raw_value, Mapping):
            # Короткая форма: поле -> JSON/путь.
            fields: List[MultipartJsonField] = []
            for field_name, payload in raw_value.items():
                resolved_payload = cls._resolve_json_payload(payload, base_dir, env_map)
                fields.append(MultipartJsonField(field_name=str(field_name), payload=resolved_payload))
            return fields
        if not isinstance(raw_value, list):
            raise ValueError("Поле multipart_json_fields должно быть списком или словарём")

        fields = []
        for entry in raw_value:
            if not isinstance(entry, Mapping):
                raise ValueError("Элемент multipart_json_fields должен быть объектом")
            field_name = entry.get("field_name") or entry.get("field") or entry.get("name")
            if not field_name:
                raise ValueError("В multipart_json_fields требуется field_name")
            payload_raw = entry.get("json")
            if payload_raw is None and "payload" in entry:
                payload_raw = entry.get("payload")
            resolved_payload = cls._resolve_json_payload(payload_raw, base_dir, env_map)
            encoding = entry.get("encoding")
            fields.append(
                MultipartJsonField(field_name=str(field_name), payload=resolved_payload, encoding=encoding)
            )
        return fields

    @staticmethod
    def _parse_wait_for(raw_value: Any) -> Optional[WaitForConfig]:
        if not raw_value:
            return None
        if isinstance(raw_value, str):
            return WaitForConfig(path=raw_value)
        if not isinstance(raw_value, Mapping):
            raise ValueError("Поле wait_for должно быть строкой или объектом")

        path = raw_value.get("path") or raw_value.get("json_path") or raw_value.get("field")
        if not path:
            raise ValueError("В wait_for требуется path")
        attempts = max(int(raw_value.get("attempts", raw_value.get("retries", 1))), 1)
        delay = max(float(raw_value.get("delay", raw_value.get("interval", 0))), 0.0)
        return WaitForConfig(path=str(path), attempts=attempts, delay=delay)

    @staticmethod
    def _parse_delay(raw_value: Any) -> Optional[float]:
        if raw_value is None:
            return None
        delay = max(float(raw_value), 0.0)
        return delay
