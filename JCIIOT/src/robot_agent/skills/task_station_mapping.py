"""Validate planner station ids against the active competition task.

The LLM may see older reference SOP examples whose human station labels map to
different semantic ids. Skills are the last player-editable boundary before
execution, so resolve the authoritative source / target from the locked task
catalog using the backend's current environment name. No scene coordinate or
level-specific station id is stored in this module.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any


logger = logging.getLogger(__name__)

_TASK_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "knowledge" / "task_config.json"
)
_STATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])((?:aux_)?(?:input|output)_\d+)(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)


def _station_role(station_name: str) -> str | None:
    name = str(station_name).lower()
    if name.startswith("output_") or name.startswith("aux_output_"):
        return "target"
    if name.startswith("input_") or name.startswith("aux_input_"):
        return "source"
    return None


def _station_token(value: Any) -> str | None:
    match = _STATION_PATTERN.search(str(value or ""))
    return match.group(1) if match else None


def _runtime_task(backend) -> dict[str, Any] | None:
    """Return the unique task matching the backend environment, if available."""
    env_name = str(getattr(backend, "_env_name", "") or "")
    if not env_name or not _TASK_CONFIG_PATH.exists():
        return None

    try:
        catalog = json.loads(_TASK_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("runtime task catalog could not be read: %s", exc)
        return None

    matches = [
        task
        for task in catalog.get("tasks", [])
        if isinstance(task, dict)
        and str(task.get("env_name") or "") == env_name
    ]
    if len(matches) != 1:
        logger.warning(
            "runtime task mapping is not unique for env=%s: matches=%d",
            env_name,
            len(matches),
        )
        return None
    return matches[0]


def configured_task(backend) -> dict[str, Any] | None:
    """Return a defensive copy of the active task's authoritative metadata.

    Skill implementations may need more than the source / target station id
    (for example, the ordered object list in a multi-object task).  Keep that
    lookup centralized here so skills never embed a level name, scene name, or
    object name of their own.
    """
    task = _runtime_task(backend)
    return dict(task) if task is not None else None


def configured_task_objects(backend) -> list[str]:
    """Return the active task's ordered object names."""
    task = _runtime_task(backend)
    if task is None:
        return []
    value = task.get("object")
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def configured_station_for_role(backend, role: str) -> str | None:
    """Return the configured source or target for the current environment."""
    if role not in {"source", "target"}:
        raise ValueError("role must be 'source' or 'target'")
    task = _runtime_task(backend)
    if task is None:
        return None
    station = str(task.get(role) or "").strip()
    return station if _station_role(station) == role else None


def resolve_configured_station(
    backend,
    requested: Any,
    *,
    role: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Resolve a planner station through the current task configuration."""
    requested_text = str(requested or "").strip()
    token = _station_token(requested_text)
    inferred_role = _station_role(token) if token else None
    resolved_role = role or inferred_role
    if resolved_role not in {"source", "target"}:
        return requested_text, None

    # Never reinterpret an explicit station of the opposite role.
    if inferred_role is not None and inferred_role != resolved_role:
        return requested_text, None

    task = _runtime_task(backend)
    if task is None:
        return requested_text, None

    configured = configured_station_for_role(backend, resolved_role)
    if not configured:
        return requested_text, None

    compared = token or requested_text
    if compared == configured:
        return configured, None

    audit = {
        "requested_station": requested_text,
        "planner_station_token": token,
        "resolved_station": configured,
        "role": resolved_role,
        "environment": str(task.get("env_name") or ""),
        "level": str(task.get("level") or ""),
        "authority": str(_TASK_CONFIG_PATH),
    }
    logger.warning(
        "corrected planner station for %s/%s: %r -> %r",
        audit["environment"],
        resolved_role,
        requested_text,
        configured,
    )
    return configured, audit
