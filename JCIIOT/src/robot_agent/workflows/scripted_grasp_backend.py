"""Programmatic grasp controller owned by the player backend adapter.

This module is intentionally outside the skill layer.  It implements the
physical backend capability used by ``SemanticBackendAdapter`` while leaving
all organizer-owned environment and controller sources unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEACHER_CACHE_PATH = (
    PROJECT_ROOT / "team_submission" / "cache" / "official_teacher_standoff.json"
)


def _base_env(env):
    return getattr(env, "unwrapped", env)


def _live_object_center(env, object_name: str) -> tuple[np.ndarray, str]:
    """Read object geometry inside the player backend implementation."""
    raw = _base_env(env)
    for site_name in (
        f"{object_name}_center_site",
        f"{object_name}_default_site",
    ):
        try:
            site_id = raw.sim.model.site_name2id(site_name)
            position = np.asarray(raw.sim.data.site_xpos[site_id], dtype=float)
            return position[:3].copy(), f"MuJoCo site {site_name}"
        except Exception:
            pass
    for joint_name in (f"{object_name}_joint0", f"{object_name}_free"):
        try:
            qpos = np.asarray(
                raw.sim.data.get_joint_qpos(joint_name), dtype=float
            ).reshape(-1)
            if qpos.size >= 3:
                return qpos[:3].copy(), f"MuJoCo joint {joint_name}"
        except Exception:
            pass
    raise RuntimeError(f"Cannot read live centre for object {object_name!r}")


def _actual_base_pose(env) -> tuple[np.ndarray, float]:
    raw = _base_env(env)
    robot = raw.robots[0]
    site_name = robot.robot_model.base.correct_naming("center")
    site_id = raw.sim.model.site_name2id(site_name)
    xy = np.asarray(raw.sim.data.site_xpos[site_id], dtype=float)[:2]
    matrix = np.asarray(raw.sim.data.site_xmat[site_id], dtype=float).reshape(3, 3)
    return xy.copy(), float(np.arctan2(matrix[1, 0], matrix[0, 0]))


@lru_cache(maxsize=1)
def official_teacher_standoff() -> dict:
    """Load or measure the organizer L1 teacher's object-relative standoff.

    Cached data is accepted only when its SHA-256 matches the organizer
    collector source. A changed upstream source therefore forces a fresh
    measurement; no task coordinate is embedded in player code.
    """
    import robosuite as suite
    from robosuite.environments.factory_sorting import (
        factory_sorting_1_3fo3erfhisem,  # noqa: F401
    )
    from robosuite.environments.factory_sorting import (
        load_factory_sorting_1_3fo3erfhisem_collect as teacher,
    )

    source_path = Path(teacher.__file__).resolve()
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if TEACHER_CACHE_PATH.exists():
        try:
            cached = json.loads(TEACHER_CACHE_PATH.read_text(encoding="utf-8"))
            standoff = float(cached.get("standoff_m"))
            if (
                cached.get("source_sha256") == source_sha256
                and math.isfinite(standoff)
                and standoff > 0.0
            ):
                cached["cache_hit"] = True
                return cached
        except Exception:
            pass

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
            env, teacher.DEFAULT_OBJECT_NAME
        )
        forward = np.array([np.cos(base_yaw), np.sin(base_yaw)], dtype=float)
        standoff = float(np.dot(object_center[:2] - base_xy, forward))
        if not math.isfinite(standoff) or standoff <= 0.0:
            raise RuntimeError(
                f"Organizer L1 teacher produced invalid standoff {standoff}"
            )
        result = {
            "version": 1,
            "standoff_m": standoff,
            "source": source_path.relative_to(PROJECT_ROOT).as_posix(),
            "source_sha256": source_sha256,
            "teacher_environment": teacher.DEFAULT_ENV_NAME,
            "teacher_object": teacher.DEFAULT_OBJECT_NAME,
            "teacher_base_xy": base_xy.tolist(),
            "teacher_base_yaw": base_yaw,
            "teacher_object_center": object_center.tolist(),
            "teacher_object_center_source": center_source,
            "cache_hit": False,
        }
    finally:
        env.close()

    try:
        TEACHER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TEACHER_CACHE_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
    return result


def resolve_object_aligned_pose(env, object_name: str, yaw: float) -> dict:
    """Derive the per-instance base pose from live object geometry."""
    object_center, center_source = _live_object_center(env, object_name)
    calibration = official_teacher_standoff()
    forward = np.array([np.cos(yaw), np.sin(yaw)], dtype=float)
    target_xy = object_center[:2] - forward * float(calibration["standoff_m"])
    return {
        "xy": target_xy.tolist(),
        "yaw": float(yaw),
        "robot_base_pos": [float(target_xy[0]), float(target_xy[1]), 0.0],
        "robot_base_ori": [0.0, 0.0, float(yaw)],
        "object_center": object_center.tolist(),
        "object_center_source": center_source,
        "teacher_calibration": calibration,
        "formula": (
            "live_object_xy - heading(semantic/configured_yaw) * "
            "organizer_L1_teacher_standoff"
        ),
    }


def _scripted_motion_step_scale() -> float:
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    data = json.loads(params_path.read_text(encoding="utf-8"))
    value = float(
        data.get("grasp_policy", {}).get("scripted_motion_step_scale", 1.0)
    )
    if not 0.50 <= value <= 1.50:
        raise ValueError(
            "grasp_policy.scripted_motion_step_scale must be in [0.50, 1.50]"
        )
    return value


def sync_material_object_states(source_env, destination_env) -> int:
    """Synchronize task objects inside the backend implementation."""
    from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (
        base_robosuite_env,
    )

    source = base_robosuite_env(source_env)
    destination = base_robosuite_env(destination_env)
    copied = 0
    for object_name in list(getattr(destination, "material_objects", []) or []):
        for suffix in ("_free", "_joint0"):
            joint_name = f"{object_name}{suffix}"
            try:
                qpos = source.sim.data.get_joint_qpos(joint_name).copy()
                destination.sim.data.set_joint_qpos(joint_name, qpos)
                try:
                    qvel = source.sim.data.get_joint_qvel(joint_name).copy()
                    destination.sim.data.set_joint_qvel(joint_name, qvel)
                except Exception:
                    pass
                copied += 1
                break
            except Exception:
                continue
    destination.sim.forward()
    return copied


def run_dynamic_scripted_grasp(
    env,
    object_name: str,
    *,
    render: bool = False,
    nav_env=None,
) -> dict:
    """Run the proven geometry-derived teacher inside the backend adapter."""
    from robosuite.environments.factory_sorting import (
        load_factory_sorting_1_3fo3erfhisem_collect as collector,
    )
    from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (
        base_robosuite_env,
    )
    from team_submission.training_tools.collect_factory_sorting import (
        _approach_aligned_target_positions,
    )

    raw_env = base_robosuite_env(env)
    motion_scale = _scripted_motion_step_scale()

    def scaled_steps(default: int, *, minimum: int = 1) -> int:
        return max(minimum, int(round(float(default) * motion_scale)))

    args = argparse.Namespace(
        object_name=object_name,
        up_steps=scaled_steps(collector.DEFAULT_UP_STEPS),
        xy_steps=scaled_steps(collector.DEFAULT_XY_STEPS),
        down_steps=scaled_steps(collector.DEFAULT_DOWN_STEPS),
        safe_z=collector.DEFAULT_SAFE_Z,
        site_above_clearance=collector.DEFAULT_SITE_ABOVE_CLEARANCE,
        site_below_offset=collector.DEFAULT_SITE_BELOW_OFFSET,
        arrival_tolerance=collector.DEFAULT_ARRIVAL_TOLERANCE,
        gripper_end_arrival_tolerance=(
            collector.DEFAULT_GRIPPER_END_ARRIVAL_TOLERANCE
        ),
        settle_steps=scaled_steps(collector.DEFAULT_SETTLE_STEPS, minimum=10),
        grasp_steps=scaled_steps(collector.DEFAULT_GRASP_STEPS, minimum=10),
        post_success_hold_steps=scaled_steps(
            collector.DEFAULT_POST_SUCCESS_HOLD_STEPS,
            minimum=5,
        ),
        max_action=collector.DEFAULT_MAX_ACTION,
        initial_view_steps=0,
        render_sleep=0.0,
        camera=collector.DEFAULT_CAMERA,
        show_object_sites=False,
        object_site_size=collector.DEFAULT_OBJECT_SITE_SIZE,
    )

    original_append = collector.append_current_obs
    original_sync = collector.sync_collection_model_xml
    original_targets = collector.get_target_positions
    had_ep_directory = hasattr(raw_env, "ep_directory")
    old_ep_directory = getattr(raw_env, "ep_directory", None)
    had_unwrapped = hasattr(raw_env, "unwrapped")
    old_unwrapped = getattr(raw_env, "unwrapped", None)
    original_reset = raw_env.reset

    def reset_with_current_scene(*reset_args, **reset_kwargs):
        observation = original_reset(*reset_args, **reset_kwargs)
        if nav_env is not None:
            sync_material_object_states(nav_env, raw_env)
        return observation

    collector.append_current_obs = lambda *args, **kwargs: None
    collector.sync_collection_model_xml = lambda *args, **kwargs: None
    collector.get_target_positions = _approach_aligned_target_positions
    raw_env.ep_directory = ""
    raw_env.unwrapped = raw_env
    raw_env.reset = reset_with_current_scene
    try:
        success, reason, _, _ = collector.rollout_once(
            raw_env,
            render=bool(render),
            args=args,
        )
    finally:
        collector.append_current_obs = original_append
        collector.sync_collection_model_xml = original_sync
        collector.get_target_positions = original_targets
        raw_env.reset = original_reset
        if had_ep_directory:
            raw_env.ep_directory = old_ep_directory
        else:
            delattr(raw_env, "ep_directory")
        if had_unwrapped:
            raw_env.unwrapped = old_unwrapped
        else:
            delattr(raw_env, "unwrapped")

    return {
        "success": bool(success),
        "successes": int(bool(success)),
        "num_rollouts": 1,
        "return": float(bool(success)),
        "programmatic_backend": True,
        "reason": reason,
        "motion_step_scale": motion_scale,
    }
