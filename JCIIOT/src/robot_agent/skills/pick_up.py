"""Pick-up skill — grasp and lift a target strictly through EnvBackend."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path
import re

import numpy as np

from robot_agent.core.scene_context import SceneContext
from robot_agent.core.types import ExecutionContext, SkillResult
from robot_agent.skills.base import BaseSkill
from robot_agent.skills.execution_state import (
    configured_checkpoint,
    placed_objects,
    set_configured_checkpoint,
    set_held_object,
)
from robot_agent.skills.grasp_alignment import (
    final_alignment_path,
    resolve_runtime_grasp_pose,
)
from robot_agent.skills.task_station_mapping import (
    configured_task,
    configured_task_objects,
    resolve_configured_station,
    safety_ordered_objects,
)


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROBOT_PARAMS_PATH = PROJECT_ROOT / "knowledge" / "robot_params.json"


def _configure_task_checkpoint(backend, scene_context: SceneContext) -> dict:
    """Select a team checkpoint through the backend's public configuration API."""
    params = json.loads(ROBOT_PARAMS_PATH.read_text(encoding="utf-8"))
    grasp_policy = params.get("grasp_policy", {})
    task = configured_task(scene_context)
    if task is None:
        raise RuntimeError(
            f"No task configuration matches semantic scene {scene_context.scene_name!r}"
        )
    env_name = str(task.get("env_name") or "")
    task_checkpoints = grasp_policy.get("task_checkpoints", {})
    configured = task_checkpoints.get(env_name)
    relative_path = configured or grasp_policy.get("checkpoint_path")
    if not relative_path:
        raise RuntimeError(f"No grasp checkpoint configured for {env_name!r}")

    checkpoint = Path(relative_path)
    if not checkpoint.is_absolute():
        checkpoint = (PROJECT_ROOT / checkpoint).resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(
            f"Configured grasp checkpoint does not exist: {checkpoint}"
        )

    checkpoint_text = str(checkpoint)
    backend_checkpoint = getattr(
        backend,
        "configured_checkpoint_path",
        None,
    )
    if (
        configured_checkpoint(backend) != checkpoint_text
        and backend_checkpoint != checkpoint_text
    ):
        configure = getattr(backend, "set_physics_grasp_config", None)
        if not callable(configure):
            raise RuntimeError(
                "Backend does not expose set_physics_grasp_config"
            )
        configure(
            checkpoint=checkpoint,
            device=str(grasp_policy.get("device", "cpu")),
            capture_grasp_frames=bool(
                grasp_policy.get("capture_grasp_frames", False)
            ),
        )
        set_configured_checkpoint(backend, checkpoint_text)
        logger.info(
            "pick_up selected validated checkpoint for %s: %s",
            env_name,
            checkpoint,
        )
    set_configured_checkpoint(backend, checkpoint_text)
    return {
        "environment": env_name,
        "checkpoint": checkpoint_text,
        "task_specific": bool(configured),
    }


@contextmanager
def _standardized_grasp_env_initialization(*_args, **_kwargs):
    """Compatibility shim: temporary environment lifecycle belongs to backend.

    Older offline diagnostics import this context manager.  Runtime skills no
    longer patch organizer evaluation functions or synchronize MuJoCo state.
    """
    yield


_CN_DIGIT: dict[str, str] = {
    "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8",
    "九": "9", "十": "10",
}
_CN_ROLE: dict[str, str] = {
    "进料": "input", "输入": "input", "入料": "input",
    "出料": "output", "输出": "output",
}


def _primary_object_name(value) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (list, tuple)):
        for item in value:
            name = _primary_object_name(item)
            if name:
                return name
    return None


def _resolve_station_name(target: str, scene: SceneContext) -> str:
    """Resolve natural-language station descriptions through SceneContext."""
    known = scene.all_port_names()
    if not known or target in known:
        return target

    for name in sorted(known, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
        if re.search(pattern, target):
            return name

    role, idx = _parse_role_index(target)
    if role and idx is not None:
        for name in known:
            info = scene.input_ports.get(name) or scene.output_ports.get(name)
            if info is not None and info.role == role and info.index == int(idx):
                return name
    return target


def _parse_role_index(text: str) -> tuple[str | None, int | None]:
    s = text
    for cn, digit in _CN_DIGIT.items():
        s = s.replace(cn, digit)
    match = re.search(r"(\d+)\s*[号#]?\s*([进出入输][料料入出])", s)
    if match:
        role_text = match.group(2)
        for chinese, role in _CN_ROLE.items():
            if chinese in role_text:
                return role, int(match.group(1))
    match = re.search(r"((?:aux_)?(?:input|output))\s*_?\s*(\d+)", text, re.I)
    if match:
        return match.group(1).lower(), int(match.group(2))
    return None, None


class PickUpSkill(BaseSkill):
    """Grasp through public backend capabilities and semantic-map knowledge."""

    def __init__(self, *, backend, scene_context: SceneContext | None = None) -> None:
        super().__init__(
            name="pick_up",
            description="Grasp or pick up an object",
            keywords=("pick", "grasp", "grab", "take", "lift", "collect"),
        )
        self._backend = backend
        self._scene = scene_context

    def run(self, context: ExecutionContext) -> SkillResult:
        inputs: dict = context.metadata.get("inputs", {})
        raw_target = str(inputs.get("target") or context.task)
        object_name = _primary_object_name(
            inputs.get("object_name")
            or inputs.get("obj_name")
            or inputs.get("object")
            or inputs.get("target_object")
        )
        if self._scene is None:
            return self._failure(raw_target, object_name, "scene context unavailable")

        target = _resolve_station_name(raw_target, self._scene)
        target, station_mapping = resolve_configured_station(
            self._scene,
            target,
            role="source",
        )
        if object_name is None:
            candidates = configured_task_objects(self._scene)
            if len(candidates) == 1:
                object_name = candidates[0]
            else:
                return self._failure(
                    target,
                    None,
                    "object_name is required for a multi-object task",
                )

        configured_objects = configured_task_objects(self._scene)
        requested_object_name = object_name
        safety_correction = None
        if len(configured_objects) > 1:
            completed = placed_objects(self._backend)
            remaining = [
                name
                for name in safety_ordered_objects(configured_objects)
                if name not in completed
            ]
            if not remaining:
                return self._failure(
                    target,
                    object_name,
                    "all configured task objects are already placed",
                )
            if object_name != remaining[0]:
                safety_correction = {
                    "requested_object": object_name,
                    "resolved_object": remaining[0],
                    "reason": "rear-first multi-object safety schedule",
                    "remaining_order": remaining,
                }
                object_name = remaining[0]

        grasp = getattr(self._backend, "grasp_object_physics", None)
        if not callable(grasp):
            return self._failure(
                target,
                object_name,
                "backend does not expose physics grasp",
            )

        try:
            checkpoint_selection = _configure_task_checkpoint(
                self._backend,
                self._scene,
            )
            alignment = resolve_runtime_grasp_pose(
                backend=self._backend,
                scene_context=self._scene,
                source=target,
                object_name=object_name,
            )
            current_xy = np.asarray(alignment["current_xy"], dtype=float)
            target_xy = np.asarray(alignment["xy"], dtype=float)
            if np.linalg.norm(target_xy - current_xy) > 0.01:
                path = final_alignment_path(
                    current_xy,
                    target_xy,
                    float(alignment["yaw"]),
                )
                if path and not self._backend.follow_path(path):
                    return self._failure(
                        target,
                        object_name,
                        "semantic grasp alignment path failed",
                        alignment=alignment,
                    )

            ok = bool(
                grasp(
                    target,
                    object_name=object_name,
                    initial_base_pose=alignment,
                )
            )
            if ok:
                set_held_object(self._backend, object_name)
            return SkillResult(
                skill_name=self.name,
                success=ok,
                message=f"Physics grasp {'OK' if ok else 'FAIL'}: {target}",
                payload={
                    "action": "pick_up",
                    "target": target,
                    "requested_target": raw_target,
                    "station_mapping": station_mapping,
                    "object_name": object_name,
                    "requested_object_name": requested_object_name,
                    "object_safety_correction": safety_correction,
                    "grasp_alignment": alignment,
                    "checkpoint_selection": checkpoint_selection,
                    "method": "envbackend_physics",
                    "ok": ok,
                },
            )
        except Exception as exc:
            logger.exception("physics grasp crashed")
            return self._failure(target, object_name, str(exc))

    def _failure(
        self,
        target: str,
        object_name: str | None,
        reason: str,
        *,
        alignment: dict | None = None,
    ) -> SkillResult:
        return SkillResult(
            skill_name=self.name,
            success=False,
            message=f"Physics grasp blocked: {reason}",
            payload={
                "action": "pick_up",
                "target": target,
                "object_name": object_name,
                "grasp_alignment": alignment,
                "method": "envbackend_physics",
                "ok": False,
                "reason": reason,
            },
        )
