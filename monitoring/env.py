"""Утилиты для подстановки переменных окружения в конфиге."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Mapping, Optional

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def apply_env(value: Any, env_map: Mapping[str, Any]) -> Any:
    """Рекурсивно подставляет ${VAR} из env_map в строках."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda match: _format_env_value(match, env_map), value)
    if isinstance(value, list):
        return [apply_env(item, env_map) for item in value]
    if isinstance(value, dict):
        return {key: apply_env(item, env_map) for key, item in value.items()}
    return value


def build_env_map(raw_env: Any, base_env: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Собирает env-map из os.environ и блока env в конфиге."""
    merged: Dict[str, Any] = dict(base_env or os.environ)
    if raw_env is None:
        return merged
    if not isinstance(raw_env, Mapping):
        raise ValueError("Поле env должно быть объектом")
    resolved: Dict[str, Any] = {}
    for key, value in raw_env.items():
        resolved[key] = apply_env(value, {**merged, **resolved})
    merged.update(resolved)
    return merged


def _format_env_value(match: re.Match[str], env_map: Mapping[str, Any]) -> str:
    name = match.group(1)
    if name in env_map:
        return str(env_map[name])
    return match.group(0)
