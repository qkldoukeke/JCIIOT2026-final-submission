"""Runtime grasp-base alignment using live scene and supplied teacher data."""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASK_CONFIG_PATH = PROJECT_ROOT / "knowledge" / "task_config.json"


def _base_env(env):
    return getattr(env, "unwrapped", env)


def _live_object_center(env, object_name: str) -> tuple[np.ndarray, str]:
    env = _base_env(env)
    for site_name in (
        f"{object_name}_center_site",
        f"{object_name}_default_site",
    ):
        try:
            site_id = env.sim.model.site_name2id(site_name)
            position = np.asarray(
                env.sim.data.site_xpos[site_id],
                dtype=float,
            )
            return position[:3].copy(), f"MuJoCo site {site_name}"
        except Exception:
            pass

    for joint_name in (f"{object_name}_joint0", f"{object_name}_free"):
        try:
            qpos = np.asarray(
                env.sim.data.get_joint_qpos(joint_name),
                dtype=float,
            ).reshape(-1)
            if qpos.size >= 3:
                return qpos[:3].copy(), f"MuJoCo joint {joint_name}"
        except Exception:
            pass
    raise RuntimeError(
        f"Cannot read a live centre for object {object_name!r}"
    )


def _actual_base_pose(env) -> tuple[np.ndarray, float]:
    env = _base_env(env)
    robot = env.robots[0]
    site_name = robot.robot_model.base.correct_naming("center")
    site_id = env.sim.model.site_name2id(site_name)
    xy = np.asarray(env.sim.data.site_xpos[site_id], dtype=float)[:2]
    matrix = np.asarray(
        env.sim.data.site_xmat[site_id],
        dtype=float,
    ).reshape(3, 3)
    yaw = float(np.arctan2(matrix[1, 0], matrix[0, 0]))
    return xy.copy(), yaw


@lru_cache(maxsize=1)
def official_teacher_standoff() -> dict[str, Any]:
    """Measure the object-relative distance in the supplied L1 collector."""
    import robosuite as suite
    from robosuite.environments.factory_sorting import (
        factory_sorting_1_3fo3erfhisem,  # noqa: F401
    )
    from robosuite.environments.factory_sorting import (
        load_factory_sorting_1_3fo3erfhisem_collect as teacher,
    )

    args = argparse.Namespace(
        controller=None,
        gripper_types="Robotiq140Gripper",
        robot_base_pos=list(teacher.DEFAULT_ROBOT_BASE_POS),
        robot_base_ori=list(teacher.DEFAULT_ROBOT_BASE_ORI),
        renderer="mjviewer",
        camera=teacher.DEFAULT_CAMERA,
        camera_height=teacher.DEFAULT_CAMERA_HEIGHT,
        camera_width=teacher.DEFAULT_CAMERA_WIDTH,
        seed=0,
    )
    env = suite.make(
        env_name=teacher.DEFAULT_ENV_NAME,
        **teacher.make_env_kwargs(args, render=False),
    )
    try:
        env.reset()
        base_xy, base_yaw = _actual_base_pose(env)
        object_center, center_source = _live_object_center(
            env,
            teacher.DEFAULT_OBJECT_NAME,
        )
        forward = np.array(
            [np.cos(base_yaw), np.sin(base_yaw)],
            dtype=float,
        )
        standoff = float(
            np.dot(object_center[:2] - base_xy, forward)
        )
        if not np.isfinite(standoff) or standoff <= 0:
            raise RuntimeError(
                f"Official L1 teacher produced invalid standoff {standoff}"
            )
        return {
            "standoff_m": standoff,
            "teacher_environment": teacher.DEFAULT_ENV_NAME,
            "teacher_object": teacher.DEFAULT_OBJECT_NAME,
            "teacher_base_xy": base_xy.tolist(),
            "teacher_base_yaw": base_yaw,
            "teacher_object_center": object_center.tolist(),
            "teacher_object_center_source": center_source,
            "authority": str(Path(teacher.__file__).resolve()),
        }
    finally:
        env.close()


def configured_grasp_yaw(
    source: str,
    *,
    backend=None,
    object_center: np.ndarray | None = None,
) -> tuple[float, str]:
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

    scene_context = getattr(backend, "_scene_context", None)
    if scene_context is None:
        raise RuntimeError(
            f"No configured grasp yaw exists for source {source!r}, "
            "and semantic-map alignment is unavailable"
        )
    try:
        station = (
            scene_context.input_ports.get(source)
            or scene_context.output_ports.get(source)
        )
        if station is None:
            raise KeyError(source)
        approach = np.asarray(
            scene_context.approach_xy(source),
            dtype=float,
        ).reshape(2)
        station_center = np.asarray(
            station.center,
            dtype=float,
        ).reshape(-1)[:2]
    except Exception as exc:
        raise RuntimeError(
            f"No complete semantic-map station record exists for source {source!r}"
        ) from exc

    direction = station_center - approach
    if not np.all(np.isfinite(direction)) or np.linalg.norm(direction) < 1e-6:
        raise RuntimeError(
            f"Semantic station approach and centre do not define "
            f"a grasp yaw for source {source!r}"
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
    source: str,
    object_name: str,
) -> dict[str, Any]:
    """Resolve a model-aligned base pose without scene-specific constants."""
    object_center, center_source = _live_object_center(
        backend.env,
        object_name,
    )
    yaw, yaw_source = configured_grasp_yaw(
        source,
        backend=backend,
        object_center=object_center,
    )
    calibration = official_teacher_standoff()
    forward = np.array([np.cos(yaw), np.sin(yaw)], dtype=float)
    target_xy = (
        object_center[:2]
        - forward * float(calibration["standoff_m"])
    )
    current_xy, current_yaw = backend.get_base_pose()
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
        "object_center": object_center.tolist(),
        "object_center_source": center_source,
        "teacher_calibration": calibration,
        "yaw_source": yaw_source,
        "formula": (
            "live_object_xy - heading(configured_yaw) * "
            "official_L1_teacher_standoff"
        ),
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
