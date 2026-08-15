"""Grasp-base alignment derived from semantic knowledge and EnvBackend state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from robot_agent.core.scene_context import SceneContext


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASK_CONFIG_PATH = PROJECT_ROOT / "knowledge" / "task_config.json"


def configured_grasp_yaw(
    source: str,
    *,
    scene_context: SceneContext,
) -> tuple[float, str]:
    """Resolve grasp yaw from locked task knowledge or semantic geometry."""
    config = json.loads(TASK_CONFIG_PATH.read_text(encoding="utf-8"))
    poses = config.get("grasp_poses", {})
    lookup_source = source
    entry = poses.get(lookup_source) if isinstance(poses, dict) else None
    if entry is None and source.startswith("line_"):
        lookup_source = "input_" + source.removeprefix("line_")
        entry = poses.get(lookup_source)
    if isinstance(entry, dict) and entry.get("yaw") is not None:
        return (
            float(entry["yaw"]),
            f"{TASK_CONFIG_PATH} grasp_poses.{lookup_source}.yaw",
        )

    station = (
        scene_context.input_ports.get(source)
        or scene_context.output_ports.get(source)
    )
    if station is None or station.approach is None:
        raise RuntimeError(
            f"No complete semantic-map station record exists for source {source!r}"
        )
    approach = np.asarray(station.approach, dtype=float).reshape(-1)[:2]
    station_center = np.asarray(station.center, dtype=float).reshape(-1)[:2]
    direction = station_center - approach
    if not np.all(np.isfinite(direction)) or np.linalg.norm(direction) < 1e-6:
        raise RuntimeError(
            f"Semantic station approach and centre do not define a grasp yaw "
            f"for source {source!r}"
        )
    return (
        float(np.arctan2(direction[1], direction[0])),
        (
            f"direction from semantic-map {source}.approach "
            f"to semantic-map {source}.center"
        ),
    )


def resolve_runtime_grasp_pose(
    *,
    backend,
    scene_context: SceneContext,
    source: str,
    object_name: str,
) -> dict[str, Any]:
    """Resolve the BC initial pose without reading MuJoCo from the skill layer.

    The semantic map already supplies the organizer-defined navigation approach
    for every task station.  Runtime robot state is read only through the public
    ``EnvBackend.get_base_pose`` method.
    """
    station = (
        scene_context.input_ports.get(source)
        or scene_context.output_ports.get(source)
    )
    if station is None or station.approach is None:
        raise RuntimeError(
            f"No semantic-map approach exists for grasp source {source!r}"
        )
    target_xy = np.asarray(station.approach, dtype=float).reshape(-1)[:2]
    if target_xy.size != 2 or not np.all(np.isfinite(target_xy)):
        raise RuntimeError(f"Invalid semantic grasp approach for {source!r}")

    yaw, yaw_source = configured_grasp_yaw(
        source,
        scene_context=scene_context,
    )
    current_xy, current_yaw = backend.get_base_pose()
    station_center = np.asarray(station.center, dtype=float).reshape(-1)[:2]
    return {
        "xy": target_xy.tolist(),
        "yaw": yaw,
        "robot_base_pos": [
            float(target_xy[0]),
            float(target_xy[1]),
            0.0,
        ],
        "robot_base_ori": [0.0, 0.0, yaw],
        "current_xy": np.asarray(current_xy, dtype=float).tolist(),
        "current_yaw": float(current_yaw),
        "object_name": object_name,
        "station_center_xy": station_center.tolist(),
        "position_source": f"semantic-map {source}.approach",
        "yaw_source": yaw_source,
        "formula": "semantic station approach + configured/semantic station yaw",
    }


def final_alignment_path(
    current_xy,
    target_xy,
    yaw: float,
) -> list[np.ndarray]:
    """Move laterally outside the station, then approach along robot heading."""
    current = np.asarray(current_xy, dtype=float).reshape(2)
    target = np.asarray(target_xy, dtype=float).reshape(2)
    forward = np.array([np.cos(yaw), np.sin(yaw)], dtype=float)
    delta = target - current
    forward_delta = forward * float(np.dot(delta, forward))
    lateral_waypoint = target - forward_delta
    path: list[np.ndarray] = []
    if np.linalg.norm(lateral_waypoint - current) > 1e-6:
        path.append(lateral_waypoint)
    if np.linalg.norm(target - lateral_waypoint) > 1e-6:
        path.append(target)
    return path
