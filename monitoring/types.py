"""Dataclass-описания конфигурации мониторинга."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class FileUploadConfig:
    """Параметры отправки файла в HTTP-запросе."""

    path: str
    field_name: str = "file"
    content_type: Optional[str] = None

    def resolved_path(self) -> Path:
        return Path(self.path).expanduser().resolve()


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
    tags: List[str] = field(default_factory=list)
    monitor_type: str = "http"
    source_path: Optional[str] = None

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any], source_path: Optional[str] = None, base_dir: Optional[Path] = None
    ) -> "HttpRouteConfig":
        file_config = raw.get("file") or raw.get("file_upload")
        file_upload = FileUploadConfig(**file_config) if file_config else None
        auth_config = raw.get("basic_auth") or raw.get("auth")
        basic_auth = BasicAuthConfig(**auth_config) if auth_config else None
        interval = max(float(raw.get("interval", 60)), 1.0)
        timeout = max(float(raw.get("timeout", 10)), 1.0)
        body_limit = int(raw.get("max_response_chars", raw.get("body_max_chars", 2048)))
        json_payload = cls._resolve_json_payload(raw.get("json"), base_dir)

        return cls(
            name=raw["name"],
            url=raw["url"],
            method=str(raw.get("method", "GET")).upper(),
            interval=interval,
            timeout=timeout,
            headers=dict(raw.get("headers", {})),
            params=dict(raw.get("params", {})),
            data=raw.get("data") or raw.get("body"),
            json_body=json_payload,
            allow_redirects=raw.get("allow_redirects", True),
            verify_ssl=raw.get("verify_ssl", True),
            ca_bundle=raw.get("ca_bundle") or raw.get("ca_cert") or raw.get("verify_path"),
            description=raw.get("description"),
            enabled=raw.get("enabled", True),
            body_max_chars=body_limit,
            file_upload=file_upload,
            basic_auth=basic_auth,
            multipart_json_field=raw.get("multipart_json_field") or raw.get("json_field"),
            tags=list(raw.get("tags", [])),
            monitor_type=raw.get("type", "http").lower(),
            source_path=source_path,
        )

    @staticmethod
    def _resolve_json_payload(payload: Any, base_dir: Optional[Path]) -> Any:
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
                    return json.loads(content or "null")
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON content in {file_path}: {exc}") from exc

        return payload
