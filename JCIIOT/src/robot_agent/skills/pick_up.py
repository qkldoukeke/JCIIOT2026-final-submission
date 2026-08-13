"""Pick-up skill — grasp and lift a target object via backend."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path
import re
import time

import numpy as np

from robot_agent.core.scene_context import SceneContext
from robot_agent.core.types import ExecutionContext, SkillResult
from robot_agent.skills.base import BaseSkill
from robot_agent.skills.grasp_alignment import (
    final_alignment_path,
    resolve_runtime_grasp_pose,
)
from robot_agent.skills.task_station_mapping import resolve_configured_station

logger = logging.getLogger(__name__)


def _scripted_first_with_bc_recovery_enabled() -> bool:
    """Read the per-version grasp router setting from the allowed config."""
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    try:
        data = json.loads(params_path.read_text(encoding="utf-8"))
        grasp_policy = data.get("grasp_policy", {})
        return bool(
            grasp_policy.get("scripted_first_with_bc_recovery", False)
        )
    except Exception:
        logger.exception("failed to read grasp skill-router configuration")
        return False


def _configure_task_checkpoint(backend) -> dict:
    """Select the validated BC recovery model for the active environment.

    Both this skill and ``knowledge/robot_params.json`` are organizer-approved
    modification points. The organizer-owned backend is left unchanged and is
    configured through its existing ``set_physics_grasp_config`` interface.
    """
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    data = json.loads(params_path.read_text(encoding="utf-8"))
    grasp_policy = data.get("grasp_policy", {})
    env_name = str(getattr(backend, "_env_name", "") or "")
    task_checkpoints = grasp_policy.get("task_checkpoints", {})
    configured = task_checkpoints.get(env_name)
    relative_path = configured or grasp_policy.get("checkpoint_path")
    if not relative_path:
        raise RuntimeError(
            f"No grasp checkpoint configured for environment {env_name!r}"
        )

    checkpoint = Path(relative_path)
    if not checkpoint.is_absolute():
        checkpoint = (params_path.parents[1] / checkpoint).resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(
            f"Configured grasp checkpoint does not exist: {checkpoint}"
        )

    current = getattr(backend, "_physics_checkpoint", None)
    if current is None or Path(current).resolve() != checkpoint:
        backend.set_physics_grasp_config(
            checkpoint=checkpoint,
            device=str(getattr(backend, "_physics_device", "cpu")),
            object_map=dict(
                getattr(backend, "_physics_object_map", {}) or {}
            ),
            capture_grasp_frames=bool(
                getattr(backend, "_capture_grasp_frames", False)
            ),
        )
        logger.info(
            "pick_up selected validated checkpoint for %s: %s",
            env_name,
            checkpoint,
        )
    return {
        "environment": env_name,
        "checkpoint": str(checkpoint),
        "task_specific": bool(configured),
    }


def _temporary_grasp_viewer_enabled() -> bool:
    """Control only the secondary human viewer, never policy observations."""
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    try:
        data = json.loads(params_path.read_text(encoding="utf-8"))
        return bool(
            data.get("grasp_policy", {}).get(
                "show_temporary_grasp_viewer",
                True,
            )
        )
    except Exception:
        logger.exception("failed to read temporary grasp viewer configuration")
        return True


def _bc_execution_adapter_config() -> tuple[float | None, float | None, bool]:
    """Read team BC execution constraints from the allowed parameter file."""
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    try:
        data = json.loads(params_path.read_text(encoding="utf-8"))
        grasp_policy = data.get("grasp_policy", {})
        raw_limit = grasp_policy.get("arm_action_slew_limit")
        limit = None if raw_limit is None else float(raw_limit)
        if limit is not None and limit <= 0.0:
            limit = None
        raw_alpha = grasp_policy.get("arm_translation_ema_alpha")
        ema_alpha = None if raw_alpha is None else float(raw_alpha)
        if ema_alpha is not None and not 0.0 < ema_alpha <= 1.0:
            raise ValueError("arm_translation_ema_alpha must be in (0, 1]")
        zero_rotation = bool(
            grasp_policy.get("zero_arm_rotation_actions", False)
        )
        return limit, ema_alpha, zero_rotation
    except Exception:
        logger.exception("failed to read BC execution-adapter configuration")
        return None, None, False


class _ArmTranslationEmaPolicy:
    """Smooth dual-arm translation while preserving gripper timing."""

    _TRANSLATION_INDICES = np.asarray([0, 1, 2, 6, 7, 8], dtype=int)

    def __init__(self, policy, alpha: float):
        self.policy = policy
        self.alpha = float(alpha)
        self._previous = np.zeros(6, dtype=float)

    def start_episode(self):
        self._previous.fill(0.0)
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    def __call__(self, *, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1).copy()
        if action.size < 12:
            raise RuntimeError(
                f"BC policy action has {action.size} values; expected at least 12"
            )
        current = action[self._TRANSLATION_INDICES]
        filtered = self.alpha * current + (1.0 - self.alpha) * self._previous
        action[self._TRANSLATION_INDICES] = filtered
        self._previous = filtered.copy()
        return action


class _ArmActionSlewLimiter:
    """Apply the gradual dual-arm action changes present in team demos."""

    def __init__(self, policy, limit: float):
        self.policy = policy
        self.limit = float(limit)
        self._previous = np.zeros(12, dtype=float)

    def start_episode(self):
        self._previous = np.zeros(12, dtype=float)
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    def __call__(self, *, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1)
        if action.size < 12:
            raise RuntimeError(
                f"BC policy action has {action.size} values; expected at least 12"
            )
        limited = action.copy()
        limited[:12] = self._previous + np.clip(
            action[:12] - self._previous,
            -self.limit,
            self.limit,
        )
        self._previous = limited[:12].copy()
        return limited


class _ZeroArmRotationPolicy:
    """Suppress untrained OSC rotations while preserving learned translation."""

    _ROTATION_INDICES = np.asarray([3, 4, 5, 9, 10, 11], dtype=int)

    def __init__(self, policy):
        self.policy = policy

    def start_episode(self):
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    def __call__(self, *, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1).copy()
        if action.size < 12:
            raise RuntimeError(
                f"BC policy action has {action.size} values; expected at least 12"
            )
        action[self._ROTATION_INDICES] = 0.0
        return action


def _adapt_bc_policy(policy):
    """Wrap the learned policy with data-derived, checkpoint-agnostic guards."""
    limit, ema_alpha, zero_rotation = _bc_execution_adapter_config()
    adapted = policy
    if ema_alpha is not None:
        adapted = _ArmTranslationEmaPolicy(adapted, ema_alpha)
        logger.info(
            "pick_up BC arm-translation EMA enabled: alpha=%.6f",
            ema_alpha,
        )
    if limit is not None:
        adapted = _ArmActionSlewLimiter(adapted, limit)
        logger.info("pick_up BC arm-action slew limit enabled: %.6f", limit)
    if zero_rotation:
        adapted = _ZeroArmRotationPolicy(adapted)
        logger.info("pick_up BC dual-arm rotation actions constrained to zero")
    return adapted


def _align_navigation_yaw_for_grasp(backend, alignment: dict) -> dict:
    """Match the live navigation yaw to the data-derived BC grasp yaw.

    The BC policy runs in a temporary environment initialized with the resolved
    grasp pose. The navigation environment must have the same yaw before the
    post-grasp state is copied back; otherwise transport attachment coordinates
    are captured in the wrong base frame. Use the organizer's direct base-pose
    helpers here because sweeping the ungrasped arms around beside the station
    can collide with the table before the BC policy has positioned them.
    """
    from robosuite.environments.factory_sorting.turn_to_station import (
        DEFAULT_TURN_MAX_ITERS,
        DEFAULT_TURN_TOLERANCE,
        base_robosuite_env,
        get_base_world_pose,
        lock_base_xy,
        set_base_world_yaw_direct,
        shortest_angle,
        zero_base_velocity,
    )

    raw_env = base_robosuite_env(backend.env)
    robot = raw_env.robots[0]
    locked_base_xy, start_yaw = get_base_world_pose(raw_env, robot)
    target_yaw = float(alignment["yaw"])
    turn_config = dict(getattr(backend, "_rp", {}).get("turn", {}))
    tolerance = float(
        turn_config.get("tolerance", DEFAULT_TURN_TOLERANCE)
    )
    max_iters = int(turn_config.get("max_iters", DEFAULT_TURN_MAX_ITERS))

    if abs(shortest_angle(target_yaw - start_yaw)) > tolerance:
        set_base_world_yaw_direct(
            raw_env,
            robot,
            target_yaw=target_yaw,
            tolerance=min(tolerance, 1e-5),
            max_iters=max_iters,
        )
    lock_base_xy(raw_env, robot, locked_base_xy)
    zero_base_velocity(raw_env, robot)
    raw_env.sim.forward()

    record_frame = getattr(backend, "_record_trajectory_frame", None)
    if callable(record_frame):
        record_frame()
    if not bool(getattr(backend, "_headless", True)):
        raw_env.render()

    final_xy, final_yaw = get_base_world_pose(raw_env, robot)
    final_error = shortest_angle(target_yaw - final_yaw)
    result = {
        "success": abs(final_error) <= tolerance,
        "base_xy": final_xy.tolist(),
        "locked_base_xy": locked_base_xy.tolist(),
        "xy_drift": float(np.linalg.norm(final_xy - locked_base_xy)),
        "start_yaw": float(start_yaw),
        "target_yaw": target_yaw,
        "final_yaw": float(final_yaw),
        "final_error": float(final_error),
        "tolerance": tolerance,
        "method": "official_direct_base_yaw",
    }
    logger.info(
        "pick_up navigation yaw alignment: success=%s "
        "start_yaw=%.6f target_yaw=%.6f final_yaw=%.6f error=%.6f",
        result["success"],
        result["start_yaw"],
        result["target_yaw"],
        result["final_yaw"],
        result["final_error"],
    )
    return result


@contextmanager
def _standardized_grasp_env_initialization(
    nav_env=None,
    *,
    scripted_first_with_bc_recovery: bool = False,
):
    """Initialize the temporary robomimic grasp env before inference.

    A normal robomimic rollout resets the wrapper and restores that resulting
    state before requesting the first policy observation. Keep this adapter in
    the allowed pick-up skill so organizer-owned backend and simulation files
    remain unchanged.
    """
    from robosuite.environments.factory_sorting import (
        load_factory_sorting_evalization as evaluation,
    )

    original_make_eval_env = evaluation.make_eval_env
    original_initial_obs_reader = evaluation.current_wrapped_policy_obs
    original_grasp_runner = evaluation.run_factory_sorting_grasp_in_wrapped_env
    initial_obs_attr = "_pick_up_direct_initial_policy_obs"
    show_temporary_viewer = _temporary_grasp_viewer_enabled()

    def initialize_for_bc(env):
        """Reset once and preserve the exact first observation for BC."""
        initial_obs = env.reset()
        if nav_env is not None:
            from robot_agent.skills.grasp_fallback import (
                sync_material_object_states,
            )

            copied = sync_material_object_states(nav_env, env)
            logger.info(
                "pick_up synchronized %d current material objects into grasp env",
                copied,
            )
        state = env.get_state()
        initial_obs = env.reset_to(state)
        setattr(env, initial_obs_attr, initial_obs)
        logger.info("pick_up initialized robomimic grasp env for BC")
        return env

    def make_initialized_eval_env(*args, **kwargs):
        call_args = list(args)
        call_kwargs = dict(kwargs)
        if scripted_first_with_bc_recovery and not show_temporary_viewer:
            if len(call_args) >= 4:
                call_args[3] = False
            else:
                call_kwargs["render"] = False
            logger.info(
                "pick_up disabled only the temporary grasp viewer; "
                "offscreen rendering remains enabled"
            )
        env = original_make_eval_env(*call_args, **call_kwargs)
        if scripted_first_with_bc_recovery:
            # The scripted controller begins with its own reset and live-scene
            # synchronization.  Resetting here as well produced the misleading
            # first viewer flash and made the robot wait before every grasp.
            logger.info(
                "pick_up deferred temporary-env reset to scripted controller"
            )
            return env
        try:
            return initialize_for_bc(env)
        except Exception:
            if hasattr(env, "close"):
                env.close()
            raise

    def read_direct_initial_obs(env):
        if hasattr(env, initial_obs_attr):
            initial_obs = getattr(env, initial_obs_attr)
            delattr(env, initial_obs_attr)
            logger.info("pick_up used direct reset_to observation for BC step 0")
            return initial_obs
        return original_initial_obs_reader(env)

    def _run_scripted_grasp(env, object_name, kwargs):
        if env is None:
            env = kwargs.get("env")
        if not object_name:
            object_name = kwargs.get("object_name")
        if not object_name:
            logger.warning("pick_up cannot run grasp fallback without object_name")
            return None

        try:
            from robot_agent.skills.grasp_fallback import (
                run_dynamic_scripted_grasp,
            )

            return run_dynamic_scripted_grasp(
                env=env,
                object_name=object_name,
                render=(
                    show_temporary_viewer
                    and bool(kwargs.get("render", False))
                ),
                nav_env=nav_env,
            )
        except Exception:
            logger.exception(
                "pick_up dynamic fallback crashed for %s",
                object_name,
            )
            return None

    def run_grasp_with_fallback(*args, **kwargs):
        env = kwargs.get("env")
        object_name = kwargs.get("object_name")
        if env is None and args:
            env = args[0]

        if scripted_first_with_bc_recovery and object_name:
            started = time.perf_counter()
            logger.info(
                "pick_up skill router selected dynamic scripted grasp first "
                "for %s; BC remains the recovery policy",
                object_name,
            )
            scripted = _run_scripted_grasp(env, object_name, kwargs)
            scripted_elapsed = time.perf_counter() - started
            scripted_success = bool(
                scripted.get("success")
            ) if isinstance(scripted, dict) else False
            logger.info(
                "pick_up scripted-first result object=%s success=%s elapsed=%.3fs",
                object_name,
                scripted_success,
                scripted_elapsed,
            )
            if scripted_success:
                scripted["skill_router"] = "scripted_first_with_bc_recovery"
                scripted["router_elapsed_sec"] = scripted_elapsed
                return scripted
            logger.warning(
                "pick_up scripted-first grasp failed for %s; recovering with BC",
                object_name,
            )
            # Scripted success needs only its single reset.  If it fails, BC
            # still receives the same standardized reset/reset_to observation
            # as the legacy, proven BC-first route.
            initialize_for_bc(env)

        call_args = list(args)
        call_kwargs = dict(kwargs)
        policy = call_kwargs.get("policy")
        if policy is None and len(call_args) > 1:
            policy = call_args[1]
        if policy is not None:
            adapted_policy = _adapt_bc_policy(policy)
            if "policy" in call_kwargs:
                call_kwargs["policy"] = adapted_policy
            else:
                call_args[1] = adapted_policy

        bc_started = time.perf_counter()
        result = original_grasp_runner(*tuple(call_args), **call_kwargs)
        bc_elapsed = time.perf_counter() - bc_started
        success = bool(result.get("success")) if isinstance(result, dict) else bool(result)
        logger.info(
            "pick_up BC result object=%s success=%s elapsed=%.3fs",
            object_name,
            success,
            bc_elapsed,
        )
        if success:
            return result
        if scripted_first_with_bc_recovery:
            return result

        logger.warning(
            "pick_up BC grasp failed for %s; running dynamic scripted fallback",
            object_name,
        )
        fallback = _run_scripted_grasp(env, object_name, kwargs)
        if isinstance(fallback, dict) and bool(fallback.get("success")):
            return fallback
        if isinstance(fallback, dict):
            logger.warning(
                "pick_up dynamic fallback failed for %s: %s",
                object_name,
                fallback.get("reason"),
            )
        return result

    evaluation.make_eval_env = make_initialized_eval_env
    evaluation.current_wrapped_policy_obs = read_direct_initial_obs
    evaluation.run_factory_sorting_grasp_in_wrapped_env = run_grasp_with_fallback
    try:
        yield
    finally:
        if evaluation.make_eval_env is make_initialized_eval_env:
            evaluation.make_eval_env = original_make_eval_env
        if evaluation.current_wrapped_policy_obs is read_direct_initial_obs:
            evaluation.current_wrapped_policy_obs = original_initial_obs_reader
        if evaluation.run_factory_sorting_grasp_in_wrapped_env is run_grasp_with_fallback:
            evaluation.run_factory_sorting_grasp_in_wrapped_env = original_grasp_runner


# Chinese-number → digit
_CN_DIGIT: dict[str, str] = {
    "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8",
    "九": "9", "十": "10",
}
# Chinese role → role prefix
_CN_ROLE: dict[str, str] = {
    "进料": "input", "输入": "input", "入料": "input",
    "出料": "output", "输出": "output",
}
# Digit-word → index
_CN_INDEX: dict[str, str] = {
    "1": "1", "2": "2", "3": "3", "4": "4",
    "一": "1", "二": "2", "三": "3", "四": "4",
}
# Station kind keywords to strip from target
_CN_KIND: list[str] = ["传送带", "架子", "桌子", "箱子", "料箱", "料斗",
                        "conveyor", "shelf", "table", "bin"]


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
    """Resolve a natural-language target to a known station name.

    Examples of what this handles:
        "在1号进料口抓取目标物体" → "input_1"
        "把物品放到3号出料口"     → "output_3"
        "input_1"                  (pass-through — exact match)
    """
    known = scene.all_port_names()
    if not known:
        return target

    # 0) exact match
    if target in known:
        return target

    # 1) canonical name embedded in a description. Longest-first and token
    # boundaries keep ``aux_input_1`` distinct from ``input_1``.
    for name in sorted(known, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
        if re.search(pattern, target):
            return name

    # 2) match by (role, index) — e.g. "1号进料口" → input station #1
    role, idx = _parse_role_index(target)
    if role and idx is not None:
        desired_idx = int(idx)
        for name in known:
            info = (scene.input_ports.get(name) or
                    scene.output_ports.get(name))
            if info is None:
                continue
            if info.role == role and info.index == desired_idx:
                return name

    return target


def _parse_role_index(text: str) -> tuple[str | None, int | None]:
    """Extract (role, index) from Chinese text like "1号进料口" → ("input", 1)."""
    # Normalise Chinese digits → Arabic
    s = text
    for cn, d in _CN_DIGIT.items():
        s = s.replace(cn, d)

    # Find a digit followed by optional characters then a role word
    m = re.search(r"(\d+)\s*[号#]?\s*([进出入输][料料入出])", s)
    if m:
        digit = m.group(1)
        role_cn = m.group(2)
        for cn_word, role_prefix in _CN_ROLE.items():
            if cn_word in role_cn:
                return role_prefix, int(digit)

    # Also try "input_N" / "output_N" pattern directly
    m = re.search(r"(input|output)\s*_?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return m.group(1).lower(), int(m.group(2))

    return None, None


class PickUpSkill(BaseSkill):
    """Grasp a target object through the environment backend.

    Resolves natural-language target descriptions to known station names
    via ``SceneContext``, falling back to substring matching.
    """

    def __init__(self, *, backend, scene_context: SceneContext | None = None) -> None:
        super().__init__(
            name="pick_up",
            description="Grasp or pick up an object",
            keywords=(
                "pick", "grasp", "grab", "lift",
                "grasp", "pick", "grab", "take", "lift", "collect",
            ),
        )
        self._backend = backend
        self._scene = scene_context

    def run(self, context: ExecutionContext) -> SkillResult:
        inputs: dict = context.metadata.get("inputs", {})
        raw_target: str = (
            inputs.get("target")
            or context.task
        )
        object_name = (
            inputs.get("object_name")
            or inputs.get("obj_name")
            or inputs.get("object")
            or inputs.get("target_object")
        )
        object_name = _primary_object_name(object_name)
        initial_base_pose = inputs.get("grasp_initial_base_pose")
        if initial_base_pose is None:
            initial_base_pose = inputs.get("initial_base_pose")
        if initial_base_pose is None:
            initial_base_pose = inputs.get("base_pose")
        target = raw_target
        if self._scene is not None:
            target = _resolve_station_name(raw_target, self._scene)
            logger.info("pick_up target: %r → %r", raw_target, target)

        # Physics grasp (only mode — no teleport fallback)
        target, station_mapping = resolve_configured_station(
            self._backend,
            target,
            role="source",
        )

        if hasattr(self._backend, "grasp_object_physics"):
            try:
                checkpoint_selection = _configure_task_checkpoint(
                    self._backend
                )
                if object_name is None and hasattr(
                    self._backend,
                    "_resolve_grasp_object_name",
                ):
                    object_name = self._backend._resolve_grasp_object_name(
                        target,
                        object_name=None,
                    )
                alignment = None
                if object_name:
                    alignment = resolve_runtime_grasp_pose(
                        backend=self._backend,
                        source=target,
                        object_name=object_name,
                    )
                    current_xy = np.asarray(
                        alignment["current_xy"],
                        dtype=float,
                    )
                    target_xy = np.asarray(alignment["xy"], dtype=float)
                    if np.linalg.norm(target_xy - current_xy) > 0.01:
                        path = final_alignment_path(
                            current_xy,
                            target_xy,
                            float(alignment["yaw"]),
                        )
                        if path and not self._backend.follow_path(path):
                            return SkillResult(
                                skill_name=self.name,
                                success=False,
                                message=(
                                    "Physics grasp alignment failed before "
                                    f"policy execution: {target}"
                                ),
                                payload={
                                    "action": "pick_up",
                                    "target": target,
                                    "object_name": object_name,
                                    "grasp_alignment": alignment,
                                    "method": "physics",
                                    "ok": False,
                                },
                            )
                    yaw_alignment = _align_navigation_yaw_for_grasp(
                        self._backend,
                        alignment,
                    )
                    alignment["navigation_yaw_alignment"] = yaw_alignment
                    if not yaw_alignment["success"]:
                        return SkillResult(
                            skill_name=self.name,
                            success=False,
                            message=(
                                "Physics grasp yaw alignment failed before "
                                f"policy execution: {target}"
                            ),
                            payload={
                                "action": "pick_up",
                                "target": target,
                                "object_name": object_name,
                                "grasp_alignment": alignment,
                                "method": "physics",
                                "ok": False,
                            },
                        )
                    initial_base_pose = alignment
                    logger.info(
                        "pick_up runtime alignment: object=%s "
                        "target=(%.4f, %.4f) yaw=%.6f",
                        object_name,
                        target_xy[0],
                        target_xy[1],
                        float(alignment["yaw"]),
                    )
                scripted_first = (
                    _scripted_first_with_bc_recovery_enabled()
                )
                with _standardized_grasp_env_initialization(
                    nav_env=self._backend.env,
                    scripted_first_with_bc_recovery=scripted_first,
                ):
                    ok = self._backend.grasp_object_physics(
                        target,
                        object_name=object_name,
                        initial_base_pose=initial_base_pose,
                    )
                resolved_object = getattr(self._backend, "_held_crate_name", None) or object_name
                return SkillResult(
                    skill_name=self.name,
                    success=ok,
                    message=f"Physics grasp {'OK' if ok else 'FAIL'}: {target}",
                    payload={
                        "action": "pick_up",
                        "target": target,
                        "requested_target": raw_target,
                        "station_mapping": station_mapping,
                        "object_name": resolved_object,
                        "grasp_initial_base_pose": initial_base_pose,
                        "grasp_alignment": alignment,
                        "grasp_router": (
                            "scripted_first_with_bc_recovery"
                            if scripted_first
                            else "bc_first_with_scripted_recovery"
                        ),
                        "checkpoint_selection": checkpoint_selection,
                        "method": "physics",
                        "ok": ok,
                    },
                )
            except Exception as exc:
                logger.exception("physics grasp crashed")
                return SkillResult(
                    skill_name=self.name, success=False,
                    message=f"Physics grasp error: {exc}",
                    payload={
                        "action": "pick_up",
                        "target": target,
                        "requested_target": raw_target,
                        "station_mapping": station_mapping,
                        "object_name": object_name,
                        "grasp_initial_base_pose": initial_base_pose,
                        "error": str(exc),
                    },
                )

        # No physics configured — teleport only
        try:
            self._backend.pick_object(target)
        except Exception:
            pass
        return SkillResult(
            skill_name=self.name, success=True,
            message=f"Grasped (snap): {target}",
            payload={"action": "pick_up", "target": target, "raw_target": raw_target, "method": "teleport"},
        )
