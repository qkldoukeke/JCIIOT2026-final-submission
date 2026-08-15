"""Place-down skill — release a held object at target via backend."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import math
from pathlib import Path

import numpy as np

from robot_agent.core.scene_context import SceneContext
from robot_agent.core.types import ExecutionContext, SkillResult
from robot_agent.skills.base import BaseSkill
from robot_agent.skills.execution_state import (
    held_object,
    mark_placed_object,
    set_held_object,
)
from robot_agent.skills.pick_up import _resolve_station_name
from robot_agent.skills.task_station_mapping import (
    configured_task,
    configured_task_objects,
    resolve_configured_station,
)

logger = logging.getLogger(__name__)


def _load_safe_approach_parameters() -> dict[str, float | bool]:
    """Load tunable pre-place motion parameters from the allowed config."""
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    data = json.loads(params_path.read_text(encoding="utf-8"))
    place = data.get("place", {})
    params: dict[str, float | bool] = {
        "enabled": bool(place.get("safe_approach_enabled", True)),
        "min_turn_angle": float(
            place.get("safe_approach_min_turn_angle", 0.35)
        ),
        "attachment_scale": float(
            place.get("safe_approach_attachment_scale", 1.0)
        ),
        "margin": float(place.get("safe_approach_margin", 0.15)),
        "max_retreat": float(
            place.get("safe_approach_max_retreat", 1.30)
        ),
        "carried_radius": float(
            place.get("safe_approach_carried_radius", 0.65)
        ),
    }
    for key in (
        "min_turn_angle",
        "attachment_scale",
        "margin",
        "max_retreat",
        "carried_radius",
    ):
        value = float(params[key])
        if not np.isfinite(value) or value < 0.0:
            raise ValueError(f"place.safe_approach_{key} must be non-negative")
    if float(params["attachment_scale"]) <= 0.0:
        raise ValueError("place.safe_approach_attachment_scale must be positive")
    if float(params["max_retreat"]) <= 0.0:
        raise ValueError("place.safe_approach_max_retreat must be positive")
    return params


def _load_multi_object_place_parameters() -> dict[str, float | bool]:
    """Load data-driven multi-object table-placement settings."""
    params_path = Path(__file__).resolve().parents[3] / "knowledge" / "robot_params.json"
    data = json.loads(params_path.read_text(encoding="utf-8"))
    place = data.get("place", {})
    params: dict[str, float | bool] = {
        "enabled": bool(place.get("distribute_multi_object_slots", True)),
        # The target must stay within the scorer radius.  This is a safety
        # margin, not a task coordinate; the actual slot comes from the map.
        "score_radius": float(place.get("multi_object_score_radius", 0.80)),
        "score_margin": float(place.get("multi_object_score_margin", 0.10)),
        "spacing_scale": float(
            place.get("multi_object_slot_spacing_scale", 0.96)
        ),
    }
    score_radius = float(params["score_radius"])
    score_margin = float(params["score_margin"])
    spacing_scale = float(params["spacing_scale"])
    if not np.isfinite(score_radius) or score_radius <= 0.0:
        raise ValueError("place.multi_object_score_radius must be positive")
    if not np.isfinite(score_margin) or not 0.0 <= score_margin < score_radius:
        raise ValueError(
            "place.multi_object_score_margin must be in [0, score_radius)"
        )
    if not np.isfinite(spacing_scale) or not 0.0 < spacing_scale <= 1.0:
        raise ValueError(
            "place.multi_object_slot_spacing_scale must be in (0, 1]"
        )
    return params


def _semantic_output_record(
    scene: SceneContext,
    target: str,
) -> tuple[dict | None, Path | None]:
    """Read the active target geometry through task_config -> semantic map."""
    task = configured_task(scene)
    if task is None:
        return None, None
    prefix = str(task.get("scene_prefix") or "").strip()
    if not prefix:
        return None, None
    map_path = (
        Path(__file__).resolve().parents[3]
        / "robosuite"
        / "robosuite"
        / "environments"
        / "factory_sorting"
        / "generated_maps"
        / f"{prefix}_scene_regenerated_semantic_map.json"
    )
    if not map_path.exists():
        return None, map_path
    data = json.loads(map_path.read_text(encoding="utf-8"))
    record = data.get("output_ports", {}).get(target)
    return (record if isinstance(record, dict) else None), map_path


def _ordered_slot_multiplier(index: int) -> int:
    """Return center-first slot order: 0, -1, +1, -2, +2, ..."""
    if index <= 0:
        return 0
    distance = (index + 1) // 2
    return -distance if index % 2 else distance


def _multi_object_slot_plan(
    scene: SceneContext,
    target: str,
    held_object: str | None,
) -> dict:
    """Compute a non-overlapping target slot without embedding scene coords."""
    result = {
        "applied": False,
        "target": target,
        "object_name": held_object,
        "reason": "disabled",
    }
    params = _load_multi_object_place_parameters()
    if not bool(params["enabled"]):
        return result

    objects = configured_task_objects(scene)
    if len(objects) <= 1:
        result["reason"] = "single_object_task"
        return result
    if held_object not in objects:
        result["reason"] = "held_object_not_in_task"
        return result

    station, map_path = _semantic_output_record(scene, target)
    if station is None:
        result.update(
            {
                "reason": "semantic_target_geometry_missing",
                "semantic_map": str(map_path) if map_path else None,
            }
        )
        return result

    center = np.asarray(station.get("center"), dtype=float).reshape(-1)[:2]
    approach = np.asarray(station.get("approach"), dtype=float).reshape(-1)[:2]
    size = np.asarray(station.get("size"), dtype=float).reshape(-1)[:2]
    if center.size != 2 or approach.size != 2 or size.size != 2:
        raise RuntimeError(f"invalid semantic geometry for output {target}")
    if not (
        np.all(np.isfinite(center))
        and np.all(np.isfinite(approach))
        and np.all(np.isfinite(size))
        and np.all(size > 0.0)
    ):
        raise RuntimeError(f"non-finite semantic geometry for output {target}")

    outward = approach - center
    outward_norm = float(np.linalg.norm(outward))
    if outward_norm < 0.10:
        raise RuntimeError(f"semantic approach for {target} is too close to center")
    outward /= outward_norm
    lateral = np.array([-outward[1], outward[0]], dtype=float)

    # Project the axis-aligned table size onto the map-derived lateral axis.
    # width / object_count reproduces the scene's own three-bin spacing while
    # keeping every slot well inside the table and the scoring radius.
    lateral_width = float(np.dot(np.abs(lateral), size))
    slot_spacing = min(
        lateral_width / float(len(objects)) * float(params["spacing_scale"]),
        float(params["score_radius"]) - float(params["score_margin"]),
    )
    index = objects.index(held_object)
    multiplier = _ordered_slot_multiplier(index)
    offset = float(multiplier) * slot_spacing
    score_distance = abs(offset)
    if score_distance >= float(params["score_radius"]):
        raise RuntimeError(
            f"computed slot for {held_object} violates scoring radius"
        )

    slot_center = center + lateral * offset
    slot_approach = approach + lateral * offset
    result.update(
        {
            "applied": True,
            "reason": "dynamic_semantic_table_slot",
            "object_index": index,
            "object_count": len(objects),
            "slot_multiplier": multiplier,
            "slot_spacing_m": slot_spacing,
            "offset_from_target_center_m": score_distance,
            "center_xy": slot_center.tolist(),
            "approach_xy": slot_approach.tolist(),
            "semantic_target_center_xy": center.tolist(),
            "semantic_target_size_xy": size.tolist(),
            "semantic_map": str(map_path),
        }
    )
    return result


def _semantic_station_override(
    scene: SceneContext,
    target: str,
    slot_plan: dict,
) -> dict:
    """Build a backend-adapter station record from semantic knowledge."""
    station = scene.output_ports.get(target)
    if station is None or station.approach is None:
        raise RuntimeError(f"semantic output station is unavailable: {target}")
    center = (
        slot_plan.get("center_xy")
        if slot_plan.get("applied")
        else np.asarray(station.center, dtype=float).tolist()
    )
    approach = (
        slot_plan.get("approach_xy")
        if slot_plan.get("applied")
        else np.asarray(station.approach, dtype=float).tolist()
    )
    return {
        "center": center,
        "approach": approach,
        "kind": station.kind or "table",
        "index": max(0, int(station.index) - 1),
    }


@contextmanager
def _multi_object_output_slot_adapter(
    backend,
    scene: SceneContext | None,
    target: str,
):
    """Temporarily expose the current object's dynamic table slot."""
    carried_object = held_object(backend)
    if scene is None:
        yield {
            "applied": False,
            "target": target,
            "object_name": carried_object,
            "reason": "no_scene_context",
        }
        return
    plan = _multi_object_slot_plan(scene, target, carried_object)
    if not bool(plan.get("applied")) or scene is None:
        yield plan
        return

    scene_station = scene.output_ports.get(target)
    if scene_station is None:
        plan["applied"] = False
        plan["reason"] = "scene_context_target_missing"
        yield plan
        return

    env_station = None

    old_scene_center = np.asarray(scene_station.center, dtype=float).copy()
    old_scene_approach = (
        None
        if scene_station.approach is None
        else np.asarray(scene_station.approach, dtype=float).copy()
    )
    old_env_center = None
    old_env_approach = None
    if isinstance(env_station, dict):
        if env_station.get("center") is not None:
            old_env_center = np.asarray(env_station["center"], dtype=float).copy()
        if env_station.get("approach") is not None:
            old_env_approach = np.asarray(env_station["approach"], dtype=float).copy()

    slot_center = np.asarray(plan["center_xy"], dtype=float)
    slot_approach = np.asarray(plan["approach_xy"], dtype=float)
    scene_center = old_scene_center.copy()
    scene_center[:2] = slot_center
    scene_approach = (
        np.zeros(max(2, old_scene_center.size), dtype=float)
        if old_scene_approach is None
        else old_scene_approach.copy()
    )
    scene_approach[:2] = slot_approach
    scene_station.center = scene_center
    scene_station.approach = scene_approach

    if isinstance(env_station, dict):
        env_center = (
            np.zeros(3, dtype=float)
            if old_env_center is None
            else old_env_center.copy()
        )
        env_approach = (
            np.zeros(3, dtype=float)
            if old_env_approach is None
            else old_env_approach.copy()
        )
        env_center[:2] = slot_center
        env_approach[:2] = slot_approach
        env_station["center"] = env_center
        env_station["approach"] = env_approach

    logger.info(
        "place_down multi-object slot: object=%s index=%d/%d "
        "offset=%.3fm center=(%.3f,%.3f)",
        carried_object,
        int(plan["object_index"]) + 1,
        int(plan["object_count"]),
        float(plan["offset_from_target_center_m"]),
        slot_center[0],
        slot_center[1],
    )
    try:
        yield plan
    finally:
        scene_station.center = old_scene_center
        scene_station.approach = old_scene_approach
        if isinstance(env_station, dict):
            if old_env_center is None:
                env_station.pop("center", None)
            else:
                env_station["center"] = old_env_center
            if old_env_approach is None:
                env_station.pop("approach", None)
            else:
                env_station["approach"] = old_env_approach


def _shortest_angle(angle: float) -> float:
    return float((angle + math.pi) % (2.0 * math.pi) - math.pi)


def _prepare_safe_output_approach(
    backend,
    scene: SceneContext | None,
    target: str,
) -> dict:
    """Retreat, turn in free space, then approach the output head-on.

    Station coordinates come from the semantic map. Clearance comes from the
    live carried-object radius, so this contains no task-specific position.
    """
    params = _load_safe_approach_parameters()
    result = {
        "applied": False,
        "target": target,
        "reason": "disabled",
    }
    if not bool(params["enabled"]):
        return result
    if scene is None:
        result["reason"] = "no_scene_context"
        return result

    station = scene.output_ports.get(target)
    if station is None or station.approach is None:
        result["reason"] = "no_semantic_output_approach"
        return result

    # The skill does not inspect the backend's transport attachment or MuJoCo
    # state.  Use the conservative carried-radius parameter from the allowed
    # robot configuration; attachment synchronization remains backend-owned.
    attachment_radius = float(params["carried_radius"])

    center = np.asarray(station.center, dtype=float).reshape(-1)[:2]
    approach = np.asarray(station.approach, dtype=float).reshape(-1)[:2]
    outward = approach - center
    center_to_approach = float(np.linalg.norm(outward))
    if center_to_approach < 0.10:
        raise RuntimeError(
            f"semantic approach for {target} is too close to its center"
        )
    outward /= center_to_approach

    base_xy, start_yaw = backend.get_base_pose()
    base_xy = np.asarray(base_xy, dtype=float)
    face_yaw = float(math.atan2(center[1] - approach[1], center[0] - approach[0]))
    turn_angle = abs(_shortest_angle(face_yaw - float(start_yaw)))
    result.update(
        {
            "attachment_radius_m": attachment_radius,
            "center_to_approach_m": center_to_approach,
            "turn_angle_rad": turn_angle,
            "approach_xy": approach.tolist(),
        }
    )
    if turn_angle < float(params["min_turn_angle"]):
        result["reason"] = "already_facing_output"
        return result

    retreat_distance = min(
        float(params["max_retreat"]),
        attachment_radius * float(params["attachment_scale"])
        + float(params["margin"]),
    )
    staging = approach + outward * retreat_distance

    bounds = scene.bounds or {}
    if bounds:
        inside = (
            float(bounds.get("x_min", -np.inf)) <= staging[0]
            <= float(bounds.get("x_max", np.inf))
            and float(bounds.get("y_min", -np.inf)) <= staging[1]
            <= float(bounds.get("y_max", np.inf))
        )
        if not inside:
            raise RuntimeError(
                f"safe staging point for {target} lies outside semantic map bounds"
            )

    result.update(
        {
            "retreat_distance_m": retreat_distance,
            "staging_xy": staging.tolist(),
            "reason": "preparing",
        }
    )
    logger.info(
        "place_down safe approach: target=%s base=(%.3f,%.3f) "
        "approach=(%.3f,%.3f) staging=(%.3f,%.3f) radius=%.3f turn=%.3f",
        target,
        base_xy[0],
        base_xy[1],
        approach[0],
        approach[1],
        staging[0],
        staging[1],
        attachment_radius,
        turn_angle,
    )

    if not backend.follow_path([base_xy.copy(), staging.copy()]):
        raise RuntimeError(f"failed to retreat to safe staging point for {target}")

    # Rotation and carried-object synchronization are performed by
    # ``place_object_physics`` inside the backend.  The skill only supplies a
    # collision-aware staging / approach path through ``follow_path``.
    turned_xy, _ = backend.get_base_pose()
    if not backend.follow_path(
        [np.asarray(turned_xy, dtype=float), approach.copy()]
    ):
        raise RuntimeError(f"failed to approach {target} head-on")

    final_xy, final_yaw = backend.get_base_pose()
    result.update(
        {
            "applied": True,
            "reason": "semantic_staging_then_backend_turn",
            "final_xy": np.asarray(final_xy, dtype=float).tolist(),
            "final_yaw": float(final_yaw),
        }
    )
    return result


@contextmanager
def _semantic_output_station_adapter(
    _backend,
    _scene: SceneContext | None,
    _target: str,
):
    """Compatibility shim; station adaptation is backend-adapter owned."""
    yield


class PlaceDownSkill(BaseSkill):
    """Release a held object at the target through the environment backend.

    Resolves natural-language target descriptions to known station names
    via ``SceneContext`` (same algorithm as ``PickUpSkill``).
    """

    def __init__(self, *, backend, scene_context: SceneContext | None = None) -> None:
        super().__init__(
            name="place_down",
            description="Place down or drop an object",
            keywords=(
                "place", "put", "drop", "release",
                "place", "drop", "put", "release", "unload",
            ),
        )
        self._backend = backend
        self._scene = scene_context

    def run(self, context: ExecutionContext) -> SkillResult:
        raw_target: str = (
            context.metadata.get("inputs", {}).get("target")
            or context.task
        )
        target = raw_target
        if self._scene is None:
            return SkillResult(
                skill_name=self.name,
                success=False,
                message="Physics place blocked: scene context unavailable",
                payload={"action": "place_down", "target": raw_target},
            )
        target = _resolve_station_name(raw_target, self._scene)
        logger.info("place_down target: %r → %r", raw_target, target)

        # Physics place (only mode — no teleport fallback)
        target, station_mapping = resolve_configured_station(
            self._scene,
            target,
            role="target",
        )

        place = getattr(self._backend, "place_object_physics", None)
        if callable(place):
            try:
                with _semantic_output_station_adapter(
                    self._backend,
                    self._scene,
                    target,
                ):
                    with _multi_object_output_slot_adapter(
                        self._backend,
                        self._scene,
                        target,
                    ) as multi_object_slot:
                        station_override = _semantic_station_override(
                            self._scene,
                            target,
                            multi_object_slot,
                        )
                        safe_approach = _prepare_safe_output_approach(
                            self._backend,
                            self._scene,
                            target,
                        )
                        ok = bool(
                            place(
                                target,
                                station_override=station_override,
                            )
                        )
                if ok:
                    mark_placed_object(
                        self._backend,
                        multi_object_slot.get("object_name"),
                    )
                    set_held_object(self._backend, None)
                msg = f"Physics place {'OK' if ok else 'FAIL'}: {target}"
                if not ok:
                    logger.warning("place_down: backend rejected target=%s", target)
                return SkillResult(
                    skill_name=self.name,
                    success=ok,
                    message=msg,
                    payload={
                        "action": "place_down",
                        "target": target,
                        "requested_target": raw_target,
                        "station_mapping": station_mapping,
                        "method": "envbackend_physics",
                        "safe_approach": safe_approach,
                        "multi_object_slot": multi_object_slot,
                        "semantic_station_override": station_override,
                        "ok": ok,
                    },
                )
            except Exception as exc:
                logger.exception("physics place crashed")
                return SkillResult(
                    skill_name=self.name, success=False,
                    message=f"Physics place error: {exc}",
                    payload={
                        "action": "place_down",
                        "target": target,
                        "requested_target": raw_target,
                        "station_mapping": station_mapping,
                        "error": str(exc),
                    },
                )

        # Fail closed instead of falling back to non-physical teleportation.
        return SkillResult(
            skill_name=self.name, success=False,
            message="Physics place blocked: backend capability unavailable",
            payload={
                "action": "place_down",
                "target": target,
                "raw_target": raw_target,
                "station_mapping": station_mapping,
                "method": "envbackend_physics",
                "ok": False,
            },
        )
