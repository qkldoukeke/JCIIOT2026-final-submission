"""Data-driven FactorySorting scripted grasp collection.

Task-specific values are never stored in this file. The runtime environment,
source station, object name, scene map, navigation XY, and grasp yaw are
resolved from the competition task catalog and matching semantic map.

The arm trajectory itself reuses the official scripted collector so the
demonstration format and control sequence stay aligned with the supplied L1
example.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any

import h5py
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROBOSUITE_ROOT = PROJECT_ROOT / "robosuite"
if str(ROBOSUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(ROBOSUITE_ROOT))

import robosuite as suite  # noqa: E402
from robosuite.environments.factory_sorting import (  # noqa: E402,F401
    factory_sorting_1_3fo3erfhisem,
    factory_sorting_3_3fo3errph7x9,
    factory_sorting_5_3fo3ertpxeut,
    factory_sorting_7_3fo3erfky9rn,
    factory_sorting_9_3fo3ert2c5fp,
)
from robosuite.environments.factory_sorting import (  # noqa: E402
    load_factory_sorting_1_3fo3erfhisem_collect as official_collector,
)
from robosuite.wrappers import DataCollectionWrapper  # noqa: E402


TASK_CONFIG_PATH = PROJECT_ROOT / "knowledge" / "task_config.json"
MAPS_ROOT = (
    PROJECT_ROOT
    / "robosuite"
    / "robosuite"
    / "environments"
    / "factory_sorting"
    / "maps"
)
GENERATED_MAPS_ROOT = MAPS_ROOT.parent / "generated_maps"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return data


def _resolve_task(
    task_config: dict[str, Any],
    *,
    level: str,
    environment: str,
) -> dict[str, Any]:
    """Resolve exactly one task using caller-provided runtime identity."""
    tasks = [task for task in task_config.get("tasks", []) if isinstance(task, dict)]
    if not tasks:
        raise RuntimeError(f"No tasks found in {TASK_CONFIG_PATH}")

    level = str(level or "").strip().upper()
    environment = str(environment or "").strip()
    if not level and not environment:
        raise RuntimeError(
            "Specify --level or --environment. The collector will not choose a task."
        )

    candidates = tasks
    if level:
        candidates = [
            task for task in candidates
            if str(task.get("level") or "").strip().upper() == level
        ]
    if environment:
        candidates = [
            task for task in candidates
            if str(task.get("env_name") or "").strip() == environment
        ]

    if len(candidates) != 1:
        matches = [
            {
                "level": task.get("level"),
                "env_name": task.get("env_name"),
            }
            for task in candidates
        ]
        raise RuntimeError(
            f"Task selector did not resolve exactly one entry; matches={matches}"
        )
    return candidates[0]


def _load_scene_map(task: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    scene_prefix = str(task.get("scene_prefix") or "").strip()
    if not scene_prefix:
        raise RuntimeError("Resolved task has no scene_prefix")

    candidates = (
        GENERATED_MAPS_ROOT
        / f"{scene_prefix}_scene_regenerated_semantic_map.json",
        MAPS_ROOT / f"{scene_prefix}_scene_regenerated.json",
    )
    for path in candidates:
        if path.exists():
            return _load_json(path), path
    raise FileNotFoundError(
        "No scene map exists for task scene_prefix "
        f"{scene_prefix!r}; checked {[str(path) for path in candidates]}"
    )


def _station_record(scene_map: dict[str, Any], station_name: str) -> dict[str, Any]:
    for group_name in ("input_ports", "output_ports"):
        group = scene_map.get(group_name, {})
        if isinstance(group, dict):
            station = group.get(station_name)
            if isinstance(station, dict):
                return station
    for item in scene_map.get("objects", []):
        if isinstance(item, dict) and item.get("name") == station_name:
            return item
    raise RuntimeError(f"Station {station_name!r} is missing from the scene map")


def _resolve_object_name(task: dict[str, Any], object_index: int) -> str:
    object_names = [
        str(value).strip()
        for value in task.get("object", [])
        if str(value).strip()
    ]
    if not object_names:
        raise RuntimeError("Resolved task has no configured object names")
    if object_index < 0 or object_index >= len(object_names):
        raise RuntimeError(
            f"--object-index {object_index} is outside the configured range "
            f"0..{len(object_names) - 1}"
        )
    return object_names[object_index]


def _resolve_online_grasp_pose(
    task_config: dict[str, Any],
    task: dict[str, Any],
    scene_map: dict[str, Any],
) -> tuple[list[float], list[float], dict[str, str]]:
    """Reproduce the online move-then-pick pose contract.

    Online XY comes from ``SceneContext.approach_xy(source)``. Prefer the yaw
    explicitly supplied in ``task_config.grasp_poses[source]``. Auxiliary
    stations do not necessarily have such an entry, so their yaw is derived
    only when the matching semantic-map record supplies both ``approach`` and
    ``center``. No default angle is used.
    """
    source = str(task.get("source") or "").strip()
    if not source:
        raise RuntimeError("Resolved task has no source station")

    station = _station_record(scene_map, source)
    approach = station.get("approach")
    if not isinstance(approach, (list, tuple)) or len(approach) < 2:
        raise RuntimeError(
            f"Station {source!r} has no valid map approach; XY will not be guessed"
        )

    grasp_poses = task_config.get("grasp_poses", {})
    grasp_pose = grasp_poses.get(source) if isinstance(grasp_poses, dict) else None
    if isinstance(grasp_pose, dict) and grasp_pose.get("yaw") is not None:
        yaw = float(grasp_pose["yaw"])
        yaw_authority = (
            f"knowledge/task_config.json grasp_poses.{source}.yaw"
        )
    else:
        center = station.get("center")
        if not isinstance(center, (list, tuple)) or len(center) < 2:
            raise RuntimeError(
                f"No online grasp yaw is configured for source {source!r}, "
                "and its semantic-map station record has no valid center"
            )
        direction = np.asarray(center[:2], dtype=float) - np.asarray(
            approach[:2],
            dtype=float,
        )
        if not np.all(np.isfinite(direction)) or np.linalg.norm(direction) < 1e-6:
            raise RuntimeError(
                f"Cannot derive a grasp yaw for source {source!r}: "
                "semantic-map approach and center do not define a direction"
            )
        yaw = float(np.arctan2(direction[1], direction[0]))
        yaw_authority = (
            f"direction from {source}.approach to {source}.center "
            "in the matching semantic map"
        )

    pos = [float(approach[0]), float(approach[1]), 0.0]
    ori = [0.0, 0.0, yaw]
    authority = {
        "xy": f"{source}.approach in the matching semantic map",
        "yaw": yaw_authority,
    }
    return pos, ori, authority


def resolve_collection_spec(args: argparse.Namespace) -> dict[str, Any]:
    task_config = _load_json(TASK_CONFIG_PATH)
    task = _resolve_task(
        task_config,
        level=args.level,
        environment=args.environment,
    )
    env_name = str(task.get("env_name") or "").strip()
    if env_name not in suite.ALL_ENVIRONMENTS:
        raise RuntimeError(
            f"Environment {env_name!r} is not registered in robosuite"
        )

    scene_map, map_path = _load_scene_map(task)
    object_name = _resolve_object_name(task, args.object_index)
    robot_base_pos, robot_base_ori, authority = _resolve_online_grasp_pose(
        task_config,
        task,
        scene_map,
    )
    return {
        "level": str(task.get("level") or ""),
        "environment": env_name,
        "scene_prefix": str(task.get("scene_prefix") or ""),
        "scene_map": str(map_path),
        "source": str(task.get("source") or ""),
        "target": str(task.get("target") or ""),
        "object_name": object_name,
        "object_index": int(args.object_index),
        "robot_base_pos": robot_base_pos,
        "robot_base_ori": robot_base_ori,
        "coordinate_authority": authority,
    }


def _apply_spec(args: argparse.Namespace, spec: dict[str, Any]) -> None:
    args.object_name = spec["object_name"]
    args.robot_base_pos = spec["robot_base_pos"]
    args.robot_base_ori = spec["robot_base_ori"]
    if not args.output_name:
        level = str(spec["level"] or "task").lower()
        args.output_name = f"factory_sorting_{level}_grasp"


def _actual_base_pose(base_env) -> tuple[list[float], float]:
    robot = base_env.robots[0]
    site_name = robot.robot_model.base.correct_naming("center")
    site_id = base_env.sim.model.site_name2id(site_name)
    xy = np.asarray(base_env.sim.data.site_xpos[site_id], dtype=float)[:2]
    mat = np.asarray(base_env.sim.data.site_xmat[site_id], dtype=float).reshape(3, 3)
    yaw = float(np.arctan2(mat[1, 0], mat[0, 0]))
    return [float(xy[0]), float(xy[1])], yaw


def _live_object_center(base_env, object_name: str) -> tuple[list[float], str]:
    """Read an object centre from the live scene without a name-specific pose."""
    for site_name in (
        f"{object_name}_center_site",
        f"{object_name}_default_site",
    ):
        try:
            pos = official_collector.site_pos(base_env, site_name)
            return [float(value) for value in pos[:3]], f"MuJoCo site {site_name}"
        except Exception:
            pass

    for joint_name in (f"{object_name}_joint0", f"{object_name}_free"):
        try:
            qpos = np.asarray(
                base_env.sim.data.get_joint_qpos(joint_name),
                dtype=float,
            ).reshape(-1)
            if qpos.size >= 3:
                return (
                    [float(value) for value in qpos[:3]],
                    f"MuJoCo joint {joint_name}",
                )
        except Exception:
            pass
    raise RuntimeError(
        f"Cannot read a live centre for object {object_name!r}"
    )


def _calibrate_robot_standoff(args: argparse.Namespace) -> dict[str, Any]:
    """Measure the supplied L1 teacher's object-relative base distance.

    The numeric standoff is not duplicated here. It is measured from the
    official collector's own environment, object, base pose, and yaw.
    """
    calibration_args = argparse.Namespace(**vars(args))
    calibration_args.robot_base_pos = list(
        official_collector.DEFAULT_ROBOT_BASE_POS
    )
    calibration_args.robot_base_ori = list(
        official_collector.DEFAULT_ROBOT_BASE_ORI
    )
    calibration_args.object_name = official_collector.DEFAULT_OBJECT_NAME
    calibration_args.seed = int(args.seed)
    env_kwargs = official_collector.make_env_kwargs(
        calibration_args,
        render=False,
    )
    env = suite.make(
        env_name=official_collector.DEFAULT_ENV_NAME,
        **env_kwargs,
    )
    try:
        env.reset()
        base_env = getattr(env, "unwrapped", env)
        base_xy, base_yaw = _actual_base_pose(base_env)
        object_center, object_center_source = _live_object_center(
            base_env,
            calibration_args.object_name,
        )
        forward = np.array(
            [np.cos(base_yaw), np.sin(base_yaw)],
            dtype=float,
        )
        robot = base_env.robots[0]
        forward_reaches = {}
        teacher_grasp_sites = {}
        for arm in official_collector.ARMS:
            grasp_site = official_collector.site_pos(
                base_env,
                official_collector.object_grasp_site_name(
                    calibration_args.object_name,
                    arm,
                ),
            )
            gripper_end = official_collector.gripper_end_center_pos(
                base_env,
                robot,
                arm,
            )
            forward_reaches[arm] = float(
                np.dot(grasp_site[:2] - gripper_end[:2], forward)
            )
            teacher_grasp_sites[arm] = grasp_site.tolist()
        teacher_axis = (
            np.asarray(teacher_grasp_sites["right"][:2])
            - np.asarray(teacher_grasp_sites["left"][:2])
        )
        teacher_axis_angle = float(
            np.arctan2(teacher_axis[1], teacher_axis[0])
        )
        grasp_axis_yaw_offset = float(
            np.arctan2(
                np.sin(teacher_axis_angle - base_yaw),
                np.cos(teacher_axis_angle - base_yaw),
            )
        )
        object_delta = np.asarray(object_center[:2]) - np.asarray(base_xy)
        standoff = float(np.dot(object_delta, forward))
        lateral = float(
            forward[0] * object_delta[1] - forward[1] * object_delta[0]
        )
        if not np.isfinite(standoff) or standoff <= 0:
            raise RuntimeError(
                f"Official calibration produced invalid standoff {standoff}"
            )
        return {
            "standoff_m": standoff,
            "lateral_offset_m": lateral,
            "teacher_environment": official_collector.DEFAULT_ENV_NAME,
            "teacher_object": calibration_args.object_name,
            "teacher_base_xy": base_xy,
            "teacher_base_yaw": base_yaw,
            "teacher_object_center": object_center,
            "teacher_object_center_source": object_center_source,
            "teacher_forward_reach_by_arm_m": forward_reaches,
            "teacher_max_forward_reach_m": max(forward_reaches.values()),
            "teacher_grasp_sites": teacher_grasp_sites,
            "teacher_grasp_axis_angle": teacher_axis_angle,
            "grasp_axis_yaw_offset": grasp_axis_yaw_offset,
            "authority": str(Path(official_collector.__file__).resolve()),
        }
    finally:
        env.close()


def _probe_live_object(
    args: argparse.Namespace,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Read the selected object's pose from a matching seeded environment."""
    probe_args = argparse.Namespace(**vars(args))
    probe_args.object_name = spec["object_name"]
    probe_args.robot_base_pos = list(spec["robot_base_pos"])
    probe_args.robot_base_ori = list(spec["robot_base_ori"])
    env_kwargs = official_collector.make_env_kwargs(probe_args, render=False)
    env = suite.make(env_name=spec["environment"], **env_kwargs)
    try:
        env.reset()
        base_env = getattr(env, "unwrapped", env)
        object_center, center_source = _live_object_center(
            base_env,
            spec["object_name"],
        )
        material_objects = list(
            getattr(base_env, "material_objects", []) or []
        )
        if spec["object_name"] not in material_objects:
            raise RuntimeError(
                f"Selected object {spec['object_name']!r} is missing from "
                f"live material_objects: {material_objects}"
            )
        actual_xy, actual_yaw = _actual_base_pose(base_env)
        forward = np.array(
            [np.cos(actual_yaw), np.sin(actual_yaw)],
            dtype=float,
        )
        robot = base_env.robots[0]
        grasp_sites = {}
        gripper_ends = {}
        forward_reaches = {}
        for arm in official_collector.ARMS:
            site_name = official_collector.object_grasp_site_name(
                spec["object_name"],
                arm,
            )
            site_pos = official_collector.site_pos(base_env, site_name)
            gripper_pos = official_collector.gripper_end_center_pos(
                base_env,
                robot,
                arm,
            )
            grasp_sites[arm] = site_pos.tolist()
            gripper_ends[arm] = gripper_pos.tolist()
            forward_reaches[arm] = float(
                np.dot(site_pos[:2] - gripper_pos[:2], forward)
            )
        return {
            "object_center": object_center,
            "object_center_source": center_source,
            "actual_base_xy": actual_xy,
            "actual_base_yaw": actual_yaw,
            "grasp_sites": grasp_sites,
            "initial_gripper_end_positions": gripper_ends,
            "forward_reach_by_arm_m": forward_reaches,
            "initial_gripper_object_contact": bool(
                official_collector.gripper_touches_object(
                    base_env,
                    robot,
                    spec["object_name"],
                )
            ),
            "seed": int(args.seed),
        }
    finally:
        env.close()


def _apply_live_object_alignment(
    args: argparse.Namespace,
    spec: dict[str, Any],
) -> None:
    """Replace station-wide approach XY with the official teacher standoff.

    The online yaw remains authoritative. Only the selected object's live
    centre and the standoff measured from the supplied L1 teacher are used to
    calculate a task-local base XY.
    """
    calibration = _calibrate_robot_standoff(args)
    navigation_probe = _probe_live_object(args, spec)
    yaw = float(spec["robot_base_ori"][2])
    spec["navigation_base_ori"] = list(spec["robot_base_ori"])
    forward = np.array([np.cos(yaw), np.sin(yaw)], dtype=float)
    object_xy = np.asarray(
        navigation_probe["object_center"][:2],
        dtype=float,
    )
    resolved_xy = (
        object_xy - forward * float(calibration["standoff_m"])
    )

    spec["navigation_base_pos"] = list(spec["robot_base_pos"])
    spec["robot_base_pos"] = [
        float(resolved_xy[0]),
        float(resolved_xy[1]),
        0.0,
    ]
    spec["live_object_alignment"] = {
        "navigation_probe": navigation_probe,
        "teacher_calibration": calibration,
        "resolved_base_xy": spec["robot_base_pos"][:2],
        "preserved_online_yaw": yaw,
        "formula": (
            "live_object_xy - heading(online_yaw) * "
            "official_L1_teacher_standoff"
        ),
    }
    spec["coordinate_authority"]["xy"] = (
        "live MuJoCo object centre and standoff measured from the official "
        "L1 scripted collector"
    )
    spec["coordinate_authority"]["yaw"] = (
        spec["coordinate_authority"]["yaw"] + " (preserved unchanged)"
    )


def diagnose_environment(
    env_name: str,
    env_kwargs: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Create one environment and verify resolved pose, object, and grasp sites."""
    env = suite.make(env_name=env_name, **env_kwargs)
    try:
        env.reset()
        base_env = getattr(env, "unwrapped", env)
        object_name = spec["object_name"]
        material_objects = list(getattr(base_env, "material_objects", []) or [])
        if object_name not in material_objects:
            raise RuntimeError(
                f"Object {object_name!r} not present in live material_objects: "
                f"{material_objects}"
            )

        site_positions = {}
        initial_eef_positions = {}
        initial_gripper_end_positions = {}
        for arm in official_collector.ARMS:
            site_name = official_collector.object_grasp_site_name(object_name, arm)
            site_positions[site_name] = official_collector.site_pos(
                base_env,
                site_name,
            ).tolist()
            initial_eef_positions[arm] = official_collector.get_eef_pos(
                base_env,
                base_env.robots[0],
                arm,
            ).tolist()
            initial_gripper_end_positions[arm] = (
                official_collector.gripper_end_center_pos(
                    base_env,
                    base_env.robots[0],
                    arm,
                ).tolist()
            )
        object_center, object_center_source = _live_object_center(
            base_env,
            object_name,
        )

        actual_xy, actual_yaw = _actual_base_pose(base_env)
        requested_xy = spec["robot_base_pos"][:2]
        requested_yaw = spec["robot_base_ori"][2]
        position_error = float(
            np.linalg.norm(np.asarray(actual_xy) - np.asarray(requested_xy))
        )
        yaw_error = float(
            np.arctan2(
                np.sin(actual_yaw - requested_yaw),
                np.cos(actual_yaw - requested_yaw),
            )
        )
        return {
            "status": "PASS",
            "environment": env_name,
            "object_name": object_name,
            "requested_base_xy": requested_xy,
            "actual_base_xy": actual_xy,
            "base_position_error_m": position_error,
            "requested_base_yaw": requested_yaw,
            "actual_base_yaw": actual_yaw,
            "base_yaw_error_rad": yaw_error,
            "object_center": object_center,
            "object_center_source": object_center_source,
            "grasp_sites": site_positions,
            "initial_eef_positions": initial_eef_positions,
            "initial_gripper_end_positions": initial_gripper_end_positions,
        }
    finally:
        env.close()


def validate_hdf5(path: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "PASS",
        "path": str(Path(path).resolve()),
        "demos": [],
        "errors": [],
    }
    with h5py.File(path, "r") as hdf5_file:
        data = hdf5_file.get("data")
        if data is None:
            raise RuntimeError("HDF5 has no data group")
        report["environment"] = str(data.attrs.get("env", ""))
        for demo_name in sorted(data.keys()):
            demo = data[demo_name]
            actions = demo["actions"]
            image = demo["obs"][official_collector.DEFAULT_CAMERA + "_image"]
            item = {
                "demo": demo_name,
                "time_steps": int(actions.shape[0]),
                "action_shape": list(actions.shape),
                "max_abs_action": float(np.max(np.abs(actions[:]))),
                "image_shape": list(image.shape),
            }
            if actions.shape[0] != image.shape[0]:
                report["errors"].append(
                    f"{demo_name}: action/image length mismatch"
                )
            report["demos"].append(item)
    report["num_demos"] = len(report["demos"])
    if report["errors"]:
        report["status"] = "FAIL"
    return report


def _approach_aligned_target_positions(
    env,
    object_name: str,
    site_below_offset: float,
):
    """Orient the live grasp-site template toward the robot approach side.

    The supplied scene remains untouched. The object's live centre and its
    supplied pair of grasp sites provide the template's depth, span, and
    height. The robot's live base position selects which object side is near.
    """
    site_names = {
        arm: official_collector.object_grasp_site_name(object_name, arm)
        for arm in official_collector.ARMS
    }
    supplied = {
        arm: official_collector.site_pos(env, site_names[arm])
        for arm in official_collector.ARMS
    }
    object_center_values, object_center_source = _live_object_center(
        env,
        object_name,
    )
    object_center = np.asarray(object_center_values, dtype=float)
    supplied_midpoint = (
        supplied["right"] + supplied["left"]
    ) / 2.0
    supplied_axis = supplied["right"][:2] - supplied["left"][:2]
    half_span = float(np.linalg.norm(supplied_axis) / 2.0)
    near_offset = float(
        np.linalg.norm(supplied_midpoint[:2] - object_center[:2])
    )
    if half_span <= 1e-6:
        raise RuntimeError(
            f"Grasp sites for {object_name!r} do not provide a valid span"
        )

    base_xy, _ = _actual_base_pose(env)
    near_direction = np.asarray(base_xy, dtype=float) - object_center[:2]
    near_norm = float(np.linalg.norm(near_direction))
    if near_norm <= 1e-6:
        raise RuntimeError(
            "Robot base overlaps the object centre; approach side is undefined"
        )
    near_direction /= near_norm
    lateral_direction = np.array(
        [-near_direction[1], near_direction[0]],
        dtype=float,
    )
    aligned_midpoint = (
        object_center[:2] + near_direction * near_offset
    )
    supplied_axis_unit = supplied_axis / (2.0 * half_span)
    site_axis_lateral_alignment = abs(
        float(np.dot(supplied_axis_unit, lateral_direction))
    )
    midpoint_near_alignment = abs(
        float(
            np.dot(
                supplied_midpoint[:2] - object_center[:2],
                near_direction,
            )
        )
    )
    orientation_consistent = (
        site_axis_lateral_alignment >= 0.75
        and midpoint_near_alignment >= near_offset * 0.75
    )

    lateral_limits = (-half_span, half_span)
    lateral_source = "supplied grasp-site span"
    near_source = "supplied grasp-site midpoint"
    if not orientation_consistent:
        collision_geoms = official_collector.object_collision_geoms(
            env,
            object_name,
        )
        collision_records = []
        for geom_name in collision_geoms:
            geom_id = env.sim.model.geom_name2id(geom_name)
            geom_xy = np.asarray(
                env.sim.data.geom_xpos[geom_id],
                dtype=float,
            )[:2]
            geom_matrix = np.asarray(
                env.sim.data.geom_xmat[geom_id],
                dtype=float,
            ).reshape(3, 3)
            geom_size = np.asarray(
                env.sim.model.geom_size[geom_id],
                dtype=float,
            )

            def projected_half_extent(direction_xy: np.ndarray) -> float:
                direction = np.array(
                    [direction_xy[0], direction_xy[1], 0.0],
                    dtype=float,
                )
                return float(
                    sum(
                        abs(float(np.dot(geom_matrix[:, axis], direction)))
                        * geom_size[axis]
                        for axis in range(3)
                    )
                )

            collision_records.append(
                {
                    "name": geom_name,
                    "xy": geom_xy,
                    "near_projection": float(
                        np.dot(
                            geom_xy - object_center[:2],
                            near_direction,
                        )
                    ),
                    "site_axis_projection": float(
                        np.dot(
                            geom_xy - object_center[:2],
                            supplied_axis_unit,
                        )
                    ),
                    "near_half_extent": projected_half_extent(
                        near_direction
                    ),
                    "lateral_half_extent": projected_half_extent(
                        lateral_direction
                    ),
                    "site_axis_half_extent": projected_half_extent(
                        supplied_axis_unit
                    ),
                }
            )
        if not collision_records:
            raise RuntimeError(
                f"Cannot resolve collision geometry for {object_name!r}"
            )
        near_wall = max(
            collision_records,
            key=lambda record: record["near_projection"],
        )
        site_axis_object_half_extent = max(
            abs(record["site_axis_projection"])
            + record["site_axis_half_extent"]
            for record in collision_records
        )
        if site_axis_object_half_extent <= 1e-6:
            raise RuntimeError(
                f"Cannot resolve object extent for {object_name!r}"
            )
        supplied_span_ratio = min(
            1.0,
            half_span / site_axis_object_half_extent,
        )
        target_half_span = (
            near_wall["lateral_half_extent"] * supplied_span_ratio
        )
        aligned_midpoint = (
            object_center[:2]
            + near_direction * near_wall["near_projection"]
        )
        lateral_limits = (-target_half_span, target_half_span)
        lateral_source = (
            "supplied site-span ratio applied to the live near wall"
        )
        near_source = (
            f"live robot-facing collision wall {near_wall['name']}"
        )

    low_lateral = (
        aligned_midpoint + lateral_direction * lateral_limits[0]
    )
    high_lateral = (
        aligned_midpoint + lateral_direction * lateral_limits[1]
    )

    robot = env.robots[0]
    gripper_xy = {
        arm: official_collector.gripper_end_center_pos(
            env,
            robot,
            arm,
        )[:2]
        for arm in official_collector.ARMS
    }
    candidate_a = {
        "right": high_lateral,
        "left": low_lateral,
    }
    candidate_b = {
        "right": low_lateral,
        "left": high_lateral,
    }

    def assignment_cost(candidate: dict[str, np.ndarray]) -> float:
        return float(
            sum(
                np.linalg.norm(candidate[arm] - gripper_xy[arm]) ** 2
                for arm in official_collector.ARMS
            )
        )

    aligned_xy = min(
        (candidate_a, candidate_b),
        key=assignment_cost,
    )
    target_z = float(supplied_midpoint[2] - site_below_offset)
    targets = {
        arm: np.array(
            [aligned_xy[arm][0], aligned_xy[arm][1], target_z],
            dtype=float,
        )
        for arm in official_collector.ARMS
    }
    print(
        "Approach-aligned grasp template: "
        f"object_center={np.round(object_center, 4).tolist()} "
        f"source={object_center_source!r}, "
        f"near_direction={np.round(near_direction, 4).tolist()}, "
        f"derived_near_offset={near_offset:.6f}, "
        f"site_half_span={half_span:.6f}, "
        f"orientation_consistent={orientation_consistent}, "
        f"lateral_limits={np.round(lateral_limits, 6).tolist()} "
        f"lateral_source={lateral_source!r}, "
        f"near_source={near_source!r}"
    )
    return targets, site_names


def _base_joint_qpos_indexes(env, robot) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for joint_name in robot.robot_model.base_joints:
        lowered = joint_name.lower()
        if "mobile_forward" in lowered:
            indexes["forward"] = env.sim.model.get_joint_qpos_addr(
                joint_name
            )
        elif "mobile_side" in lowered:
            indexes["side"] = env.sim.model.get_joint_qpos_addr(joint_name)
    missing = {"forward", "side"} - set(indexes)
    if missing:
        raise RuntimeError(
            f"Missing mobile-base qpos indexes: {sorted(missing)}"
        )
    return indexes


def _set_live_base_xy(env, target_xy: np.ndarray) -> None:
    """Set a small base XY perturbation using a measured local Jacobian."""
    env = getattr(env, "unwrapped", env)
    robot = env.robots[0]
    indexes = _base_joint_qpos_indexes(env, robot)
    qpos = env.sim.data.qpos
    original = np.array(
        [qpos[indexes["forward"]], qpos[indexes["side"]]],
        dtype=float,
    )
    base_xy, _ = _actual_base_pose(env)
    epsilon = 1e-4
    columns = []
    for axis, key in enumerate(("forward", "side")):
        qpos[indexes["forward"]] = original[0]
        qpos[indexes["side"]] = original[1]
        qpos[indexes[key]] += epsilon
        env.sim.forward()
        shifted_xy, _ = _actual_base_pose(env)
        columns.append(
            (np.asarray(shifted_xy) - np.asarray(base_xy)) / epsilon
        )
    qpos[indexes["forward"]] = original[0]
    qpos[indexes["side"]] = original[1]
    env.sim.forward()

    qpos_to_world = np.column_stack(columns)
    if abs(float(np.linalg.det(qpos_to_world))) < 1e-8:
        raise RuntimeError(
            f"Invalid mobile-base XY mapping: {qpos_to_world}"
        )
    delta_qpos = np.linalg.solve(
        qpos_to_world,
        np.asarray(target_xy, dtype=float) - np.asarray(base_xy),
    )
    qpos[indexes["forward"]] += delta_qpos[0]
    qpos[indexes["side"]] += delta_qpos[1]
    for joint_name in robot.robot_model.base_joints:
        try:
            qvel_addr = env.sim.model.get_joint_qvel_addr(joint_name)
            env.sim.data.qvel[qvel_addr] = 0.0
        except Exception:
            pass
    env.sim.forward()


def _object_joint_name(env, object_name: str) -> str:
    env = getattr(env, "unwrapped", env)
    for joint_name in (
        f"{object_name}_joint0",
        f"{object_name}_free",
    ):
        try:
            qpos = np.asarray(
                env.sim.data.get_joint_qpos(joint_name),
                dtype=float,
            ).reshape(-1)
            if qpos.size >= 3:
                return joint_name
        except Exception:
            pass
    raise RuntimeError(
        f"Cannot resolve a movable joint for object {object_name!r}"
    )


def _apply_object_xy_offset(
    env,
    object_name: str,
    offset_xy: np.ndarray,
) -> str:
    env = getattr(env, "unwrapped", env)
    joint_name = _object_joint_name(env, object_name)
    qpos = np.asarray(
        env.sim.data.get_joint_qpos(joint_name),
        dtype=float,
    ).copy()
    qpos[:2] += np.asarray(offset_xy, dtype=float)
    env.sim.data.set_joint_qpos(joint_name, qpos)
    try:
        qvel = np.asarray(
            env.sim.data.get_joint_qvel(joint_name),
            dtype=float,
        ).copy()
        qvel[:] = 0.0
        env.sim.data.set_joint_qvel(joint_name, qvel)
    except Exception:
        pass
    env.sim.forward()
    return joint_name


def _object_linear_speed(env, object_name: str) -> float | None:
    env = getattr(env, "unwrapped", env)
    try:
        joint_name = _object_joint_name(env, object_name)
        qvel = np.asarray(
            env.sim.data.get_joint_qvel(joint_name),
            dtype=float,
        ).reshape(-1)
        if qvel.size >= 3:
            return float(np.linalg.norm(qvel[:3]))
    except Exception:
        pass
    return None


def run_scripted_rollout(
    env,
    *,
    render: bool,
    args: argparse.Namespace,
):
    """Run the official policy with a configurable XY-contact gate.

    Large containers can touch a finger during the lateral approach before
    the final descent. The episode is still accepted only when the official
    final two-gripper grasp check succeeds.
    """
    original_move = official_collector.move_along_linear_segment
    original_get_targets = official_collector.get_target_positions
    raw_env = getattr(env, "env", None)
    if raw_env is None:
        raise RuntimeError(
            "Perturbed collection requires DataCollectionWrapper.env"
        )
    original_raw_reset = raw_env.reset
    stability: dict[str, Any] = {}

    def reset_with_perturbations(*reset_args, **reset_kwargs):
        result = original_raw_reset(*reset_args, **reset_kwargs)
        base_env = getattr(raw_env, "unwrapped", raw_env)
        base_offset = np.asarray(
            getattr(args, "rollout_base_xy_offset", [0.0, 0.0]),
            dtype=float,
        )
        object_offset = np.asarray(
            getattr(args, "rollout_object_xy_offset", [0.0, 0.0]),
            dtype=float,
        )
        arm_joint_offsets = np.asarray(
            getattr(args, "rollout_arm_joint_offsets", []),
            dtype=float,
        )
        current_base_xy, _ = _actual_base_pose(base_env)
        _set_live_base_xy(
            base_env,
            np.asarray(current_base_xy, dtype=float) + base_offset,
        )
        object_joint = _apply_object_xy_offset(
            base_env,
            args.object_name,
            object_offset,
        )
        robot = base_env.robots[0]
        arm_qpos_indexes = list(robot._ref_arm_joint_pos_indexes)
        arm_qvel_indexes = list(robot._ref_arm_joint_vel_indexes)
        if arm_joint_offsets.size:
            if arm_joint_offsets.size != len(arm_qpos_indexes):
                raise RuntimeError(
                    "arm joint jitter size mismatch: "
                    f"{arm_joint_offsets.size} != {len(arm_qpos_indexes)}"
                )
            base_env.sim.data.qpos[arm_qpos_indexes] += arm_joint_offsets
            base_env.sim.data.qvel[arm_qvel_indexes] = 0.0
            base_env.sim.forward()
        initial_center, center_source = _live_object_center(
            base_env,
            args.object_name,
        )
        actual_base_xy, actual_base_yaw = _actual_base_pose(base_env)
        stability.update(
            {
                "base_xy_offset": base_offset.tolist(),
                "object_xy_offset": object_offset.tolist(),
                "arm_joint_offsets": arm_joint_offsets.tolist(),
                "actual_base_xy": actual_base_xy,
                "actual_base_yaw": actual_base_yaw,
                "initial_object_center": initial_center,
                "object_center_source": center_source,
                "object_joint": object_joint,
            }
        )
        return result

    def move_with_configured_contact_gate(*move_args, **move_kwargs):
        if (
            not args.reject_xy_contact
            and move_kwargs.get("label") == "XY approach"
        ):
            move_kwargs["reject_object_contact"] = False
        return original_move(*move_args, **move_kwargs)

    official_collector.move_along_linear_segment = (
        move_with_configured_contact_gate
    )
    if args.align_grasp_sites_to_approach:
        official_collector.get_target_positions = (
            _approach_aligned_target_positions
        )
    raw_env.reset = reset_with_perturbations
    try:
        success, reason, ep_directory, obs_buffer = (
            official_collector.rollout_once(
                env,
                render=render,
                args=args,
            )
        )
        base_env = getattr(env, "unwrapped", env)
        final_center, _ = _live_object_center(
            base_env,
            args.object_name,
        )
        initial_center = np.asarray(
            stability["initial_object_center"],
            dtype=float,
        )
        final_center_array = np.asarray(final_center, dtype=float)
        horizontal_drift = float(
            np.linalg.norm(
                final_center_array[:2] - initial_center[:2]
            )
        )
        linear_speed = _object_linear_speed(
            base_env,
            args.object_name,
        )
        stability.update(
            {
                "final_object_center": final_center,
                "horizontal_drift_m": horizontal_drift,
                "final_linear_speed_mps": linear_speed,
            }
        )
        stable = (
            horizontal_drift <= args.max_object_horizontal_drift
            and (
                linear_speed is None
                or linear_speed <= args.max_object_linear_speed
            )
        )
        print(
            "Object stability: "
            f"horizontal_drift={horizontal_drift:.6f} m, "
            f"linear_speed={linear_speed}, stable={stable}"
        )
        if success and not stable:
            env.successful = False
            success = False
            reason = (
                "grasp contact passed but object stability failed: "
                f"horizontal_drift={horizontal_drift:.6f} m, "
                f"linear_speed={linear_speed}"
            )
        args.last_rollout_quality = dict(stability)
        return success, reason, ep_directory, obs_buffer
    finally:
        raw_env.reset = original_raw_reset
        official_collector.move_along_linear_segment = original_move
        official_collector.get_target_positions = original_get_targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect FactorySorting grasp demonstrations using task and map "
            "data instead of task-specific constants."
        )
    )
    selector = parser.add_argument_group("task selector")
    selector.add_argument("--level", default="", help="Task level, for example L2")
    selector.add_argument(
        "--environment",
        default="",
        help="Exact runtime env_name from task_config.json",
    )
    selector.add_argument(
        "--object-index",
        type=int,
        default=0,
        help="Index into the resolved task's object list",
    )
    selector.add_argument(
        "--resolve-only",
        action="store_true",
        help="Print the resolved task, pose, and coordinate sources without MuJoCo",
    )
    selector.add_argument(
        "--diagnose-only",
        action="store_true",
        help="Create one MuJoCo environment and verify pose/object/sites, without actions",
    )
    selector.add_argument(
        "--pose-mode",
        choices=("object-aligned", "navigation"),
        default="object-aligned",
        help=(
            "object-aligned derives grasp XY from live object state and the "
            "official teacher; navigation uses the map approach directly"
        ),
    )

    parser.add_argument(
        "--num-rollouts",
        type=int,
        default=official_collector.DEFAULT_NUM_ROLLOUTS,
    )
    parser.add_argument("--up-steps", type=int, default=official_collector.DEFAULT_UP_STEPS)
    parser.add_argument("--xy-steps", type=int, default=official_collector.DEFAULT_XY_STEPS)
    parser.add_argument("--down-steps", type=int, default=official_collector.DEFAULT_DOWN_STEPS)
    parser.add_argument("--safe-z", type=float, default=official_collector.DEFAULT_SAFE_Z)
    parser.add_argument(
        "--site-above-clearance",
        type=float,
        default=official_collector.DEFAULT_SITE_ABOVE_CLEARANCE,
    )
    parser.add_argument(
        "--site-below-offset",
        type=float,
        default=official_collector.DEFAULT_SITE_BELOW_OFFSET,
    )
    parser.add_argument(
        "--arrival-tolerance",
        type=float,
        default=official_collector.DEFAULT_ARRIVAL_TOLERANCE,
    )
    parser.add_argument(
        "--gripper-end-arrival-tolerance",
        type=float,
        default=official_collector.DEFAULT_GRIPPER_END_ARRIVAL_TOLERANCE,
    )
    parser.add_argument(
        "--settle-steps",
        type=int,
        default=official_collector.DEFAULT_SETTLE_STEPS,
    )
    parser.add_argument(
        "--grasp-steps",
        type=int,
        default=official_collector.DEFAULT_GRASP_STEPS,
    )
    parser.add_argument(
        "--post-success-hold-steps",
        type=int,
        default=official_collector.DEFAULT_POST_SUCCESS_HOLD_STEPS,
    )
    parser.add_argument(
        "--max-action",
        type=float,
        default=official_collector.DEFAULT_MAX_ACTION,
    )
    parser.add_argument(
        "--initial-view-steps",
        type=int,
        default=official_collector.DEFAULT_INITIAL_VIEW_STEPS,
    )
    parser.add_argument(
        "--render-sleep",
        type=float,
        default=official_collector.DEFAULT_RENDER_SLEEP,
    )
    parser.add_argument(
        "--camera-height",
        type=int,
        default=official_collector.DEFAULT_CAMERA_HEIGHT,
    )
    parser.add_argument(
        "--camera-width",
        type=int,
        default=official_collector.DEFAULT_CAMERA_WIDTH,
    )
    parser.add_argument(
        "--show-object-sites",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--reject-xy-contact",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Abort on object contact during lateral approach. By default "
            "contact is allowed and the final two-gripper grasp check decides."
        ),
    )
    parser.add_argument(
        "--align-grasp-sites-to-approach",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Dynamically orient the supplied grasp-site template toward the "
            "robot using only live MuJoCo geometry. This does not modify the "
            "competition scene."
        ),
    )
    perturbation = parser.add_argument_group(
        "successful-demonstration perturbations"
    )
    perturbation.add_argument(
        "--clean-rollouts",
        type=int,
        default=0,
        help=(
            "Number of initial rollouts with zero perturbation. Remaining "
            "rollouts use the configured jitter ranges."
        ),
    )
    perturbation.add_argument(
        "--base-xy-jitter",
        type=float,
        default=0.0,
        help=(
            "Uniform per-axis mobile-base XY jitter range in metres, "
            "resampled for every non-clean rollout."
        ),
    )
    perturbation.add_argument(
        "--object-xy-jitter",
        type=float,
        default=0.0,
        help=(
            "Uniform per-axis object XY jitter range in metres, resampled "
            "for every non-clean rollout."
        ),
    )
    perturbation.add_argument(
        "--arm-joint-jitter",
        type=float,
        default=0.0,
        help=(
            "Uniform per-joint initial arm-position jitter in radians. "
            "The scripted teacher then computes corrective actions from the "
            "perturbed state; only successful stable grasps are saved."
        ),
    )
    perturbation.add_argument(
        "--max-object-horizontal-drift",
        type=float,
        default=0.02,
        help=(
            "Reject an otherwise successful episode if the object moves "
            "farther than this horizontal distance during grasp."
        ),
    )
    perturbation.add_argument(
        "--max-object-linear-speed",
        type=float,
        default=0.05,
        help=(
            "Reject an otherwise successful episode if final object linear "
            "speed exceeds this value in metres per second."
        ),
    )
    parser.add_argument(
        "--object-site-size",
        type=float,
        default=official_collector.DEFAULT_OBJECT_SITE_SIZE,
    )
    parser.add_argument(
        "--directory",
        default=os.path.join(suite.models.assets_root, "demonstrations_private"),
    )
    parser.add_argument("--output-name", default="")
    parser.add_argument("--renderer", default="mjviewer")
    parser.add_argument("--camera", default=official_collector.DEFAULT_CAMERA)
    parser.add_argument("--controller", default=None)
    parser.add_argument("--gripper-types", default="Robotiq140Gripper")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed is None:
        args.seed = secrets.randbelow(2**31 - 1)
    if args.num_rollouts < 1:
        raise RuntimeError("--num-rollouts must be at least 1")
    if args.clean_rollouts < 0 or args.clean_rollouts > args.num_rollouts:
        raise RuntimeError(
            "--clean-rollouts must be between 0 and --num-rollouts"
        )
    for name in (
        "base_xy_jitter",
        "object_xy_jitter",
        "arm_joint_jitter",
        "max_object_horizontal_drift",
        "max_object_linear_speed",
    ):
        if float(getattr(args, name)) < 0:
            raise RuntimeError(f"--{name.replace('_', '-')} cannot be negative")
    spec = resolve_collection_spec(args)
    if args.pose_mode == "object-aligned" and not args.resolve_only:
        _apply_live_object_alignment(args, spec)
    _apply_spec(args, spec)
    print(json.dumps({"resolved_collection_spec": spec}, indent=2, ensure_ascii=False))
    if args.resolve_only:
        return

    render = not args.no_render and not args.diagnose_only
    env_kwargs = official_collector.make_env_kwargs(args, render=render)
    if args.diagnose_only:
        report = diagnose_environment(spec["environment"], env_kwargs, spec)
        print(json.dumps({"diagnostic": report}, indent=2, ensure_ascii=False))
        return

    dataset_env_kwargs = dict(env_kwargs)
    dataset_env_kwargs["has_renderer"] = False
    raw_env = suite.make(env_name=spec["environment"], **env_kwargs)
    tmp_directory = tempfile.mkdtemp(prefix="factory_sorting_grasp_raw_")
    env = DataCollectionWrapper(
        raw_env,
        tmp_directory,
        collect_freq=1,
        flush_freq=1000,
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    out_dir = os.path.join(args.directory, timestamp)
    hdf5_name = f"{args.output_name}_{timestamp}.hdf5"
    os.makedirs(out_dir, exist_ok=True)

    successes = 0
    obs_cache: dict[str, dict[str, list[np.ndarray]]] = {}
    perturbation_rng = np.random.default_rng(int(args.seed))
    rollout_quality: list[dict[str, Any]] = []
    try:
        for rollout_idx in range(args.num_rollouts):
            clean_rollout = rollout_idx < args.clean_rollouts
            if clean_rollout:
                base_offset = np.zeros(2, dtype=float)
                object_offset = np.zeros(2, dtype=float)
                arm_joint_offsets = np.zeros(
                    len(raw_env.robots[0]._ref_arm_joint_pos_indexes),
                    dtype=float,
                )
            else:
                base_offset = perturbation_rng.uniform(
                    -float(args.base_xy_jitter),
                    float(args.base_xy_jitter),
                    size=2,
                )
                object_offset = perturbation_rng.uniform(
                    -float(args.object_xy_jitter),
                    float(args.object_xy_jitter),
                    size=2,
                )
                arm_joint_offsets = perturbation_rng.uniform(
                    -float(args.arm_joint_jitter),
                    float(args.arm_joint_jitter),
                    size=len(raw_env.robots[0]._ref_arm_joint_pos_indexes),
                )
            args.rollout_base_xy_offset = base_offset.tolist()
            args.rollout_object_xy_offset = object_offset.tolist()
            args.rollout_arm_joint_offsets = arm_joint_offsets.tolist()
            print(
                f"\nRollout {rollout_idx + 1}/{args.num_rollouts} "
                f"clean={clean_rollout} "
                f"base_offset={np.round(base_offset, 5).tolist()} "
                f"object_offset={np.round(object_offset, 5).tolist()}"
                f" arm_joint_jitter_max={float(np.max(np.abs(arm_joint_offsets))):.5f}"
            )
            success, reason, ep_directory, obs_buffer = (
                run_scripted_rollout(
                    env,
                    render=render,
                    args=args,
                )
            )
            successes += int(success)
            if success:
                obs_cache[os.path.normpath(ep_directory)] = obs_buffer
            rollout_quality.append(
                {
                    "rollout": rollout_idx + 1,
                    "clean": clean_rollout,
                    "accepted": bool(success),
                    "reason": reason,
                    **dict(getattr(args, "last_rollout_quality", {})),
                }
            )
            print(f"Result: {reason}")
    finally:
        env.close()

    policy_info = {
        "collector": str(Path(__file__).resolve()),
        "task_resolution": spec,
        "arguments": vars(args),
        "rollout_quality": rollout_quality,
        "scripted_policy": str(Path(official_collector.__file__).resolve()),
    }
    hdf5_path, num_saved = (
        official_collector.gather_successful_demonstrations_as_hdf5(
            tmp_directory,
            out_dir,
            hdf5_name=hdf5_name,
            env_name=spec["environment"],
            env_kwargs=dataset_env_kwargs,
            policy_info=policy_info,
            obs_cache=obs_cache,
        )
    )
    print(
        f"\nAttempts: {args.num_rollouts}, successes: {successes}, "
        f"saved demos: {num_saved}"
    )
    print(f"HDF5 saved to: {hdf5_path}")
    print(f"Raw trajectory directory: {tmp_directory}")

    report = validate_hdf5(hdf5_path)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if num_saved == 0 or report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
