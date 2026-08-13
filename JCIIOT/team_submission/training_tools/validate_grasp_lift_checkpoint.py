"""Validate a FactorySorting BC checkpoint with the online grasp-and-lift gate.

Task identity, object name, base position, and base yaw are resolved through
the same task catalog and semantic-map rules used by the data collector.
Grasp and lift settings are read from knowledge/robot_params.json so this test
matches the online backend without modifying organizer-owned code.
"""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys

import h5py
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROBOSUITE_ROOT = PROJECT_ROOT / "robosuite"
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, ROBOSUITE_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from collect_factory_sorting import (  # noqa: E402
    _apply_live_object_alignment,
    _approach_aligned_target_positions,
    resolve_collection_spec,
)
from robosuite.environments.factory_sorting import (  # noqa: E402
    load_factory_sorting_1_3fo3erfhisem_collect as scripted_grasp,
)
from robosuite.environments.factory_sorting.lift_after_grasp import (  # noqa: E402
    lift_grasped_object,
)
from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (  # noqa: E402
    base_robosuite_env,
    gripper_end_center_pos,
    load_policy_and_config,
    make_eval_env,
    run_factory_sorting_grasp_in_wrapped_env,
)
from robosuite.utils import transform_utils as T  # noqa: E402


ROBOT_PARAMS_PATH = PROJECT_ROOT / "knowledge" / "robot_params.json"


def load_robot_params() -> dict:
    with ROBOT_PARAMS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--level", type=str, required=True)
    parser.add_argument("--environment", type=str, default="")
    parser.add_argument("--object-index", type=int, default=0)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--seed", type=int, default=31001)
    parser.add_argument("--policy-seed", type=int, default=None)
    parser.add_argument("--eval-steps", type=int, default=None)
    parser.add_argument(
        "--arm-action-slew-limit",
        type=float,
        default=None,
        help="Optional per-step change limit for the first 12 dual-arm actions.",
    )
    parser.add_argument(
        "--arm-translation-ema-alpha",
        type=float,
        default=None,
        help=(
            "Optional EMA coefficient for the six dual-arm translation "
            "channels. Gripper commands and rotation channels are untouched."
        ),
    )
    parser.add_argument(
        "--zero-arm-rotation-actions",
        action="store_true",
        help=(
            "Force the six OSC rotation channels to zero. The official "
            "scripted demonstrations use zero rotation actions throughout."
        ),
    )
    parser.add_argument(
        "--init-mode",
        choices=("current", "reset", "reset_to"),
        default="reset_to",
    )
    parser.add_argument("--apply-skill-initializer", action="store_true")
    parser.add_argument(
        "--trace-dataset",
        type=Path,
        default=None,
        help="Optional HDF5 whose demo_1 is used as the teacher trace reference.",
    )
    parser.add_argument(
        "--trace-every",
        type=int,
        default=25,
        help="Emit a policy-versus-teacher trace every N grasp steps.",
    )
    parser.add_argument(
        "--direct-initial-observation",
        action="store_true",
        help=(
            "Diagnostic: read the post-reset wrapped observation directly "
            "instead of advancing MuJoCo with a hidden zero-action step."
        ),
    )
    parser.add_argument(
        "--rescue-orientation-dataset",
        type=Path,
        default=None,
        help=(
            "Optional successful dataset used only to diagnose whether the "
            "failed final grasp is caused by end-effector orientation drift."
        ),
    )
    parser.add_argument(
        "--rescue-final-servo",
        action="store_true",
        help=(
            "Diagnostic: if BC misses, servo both gripper ends to live, "
            "approach-aligned object targets and close the grippers."
        ),
    )
    parser.add_argument(
        "--fallback-scripted-grasp",
        action="store_true",
        help=(
            "After a BC failure, reset the temporary grasp environment and "
            "run the proven dynamic-geometry scripted grasp without recording."
        ),
    )
    parser.add_argument(
        "--scripted-grasp-only",
        action="store_true",
        help="Skip BC rollout and validate the dynamic scripted grasp path directly.",
    )
    return parser.parse_args()


class ArmActionSlewLimiter:
    """Apply a teacher-like gradual ramp to dual-arm policy actions."""

    def __init__(self, policy, limit: float):
        if limit <= 0:
            raise ValueError("arm action slew limit must be positive")
        self.policy = policy
        self.limit = float(limit)
        self.previous = np.zeros(12, dtype=float)

    def start_episode(self):
        self.previous.fill(0.0)
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    def __call__(self, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1)
        if action.size < 12:
            raise RuntimeError(
                f"policy action has {action.size} values; expected at least 12"
            )
        limited = action.copy()
        delta = np.clip(
            limited[:12] - self.previous,
            -self.limit,
            self.limit,
        )
        limited[:12] = self.previous + delta
        self.previous = limited[:12].copy()
        return limited


class ArmTranslationEmaPolicy:
    """Smooth dual-arm translation without delaying gripper closure."""

    TRANSLATION_INDICES = np.asarray([0, 1, 2, 6, 7, 8], dtype=int)

    def __init__(self, policy, alpha: float):
        if not 0.0 < alpha <= 1.0:
            raise ValueError("arm translation EMA alpha must be in (0, 1]")
        self.policy = policy
        self.alpha = float(alpha)
        self.previous = np.zeros(6, dtype=float)

    def start_episode(self):
        self.previous.fill(0.0)
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    def __call__(self, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1).copy()
        if action.size < 12:
            raise RuntimeError(
                f"policy action has {action.size} values; expected at least 12"
            )
        current = action[self.TRANSLATION_INDICES]
        filtered = self.alpha * current + (1.0 - self.alpha) * self.previous
        action[self.TRANSLATION_INDICES] = filtered
        self.previous = filtered.copy()
        return action


class ZeroArmRotationPolicy:
    """Preserve learned translation / gripper actions and suppress rotation noise."""

    ROTATION_INDICES = np.asarray([3, 4, 5, 9, 10, 11], dtype=int)

    def __init__(self, policy):
        self.policy = policy

    def start_episode(self):
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    def __call__(self, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1).copy()
        if action.size < 12:
            raise RuntimeError(
                f"policy action has {action.size} values; expected at least 12"
            )
        action[self.ROTATION_INDICES] = 0.0
        return action


class TeacherTracePolicy:
    """Log closed-loop policy drift against one recorded teacher trajectory."""

    def __init__(self, policy, dataset: Path, every: int):
        if every <= 0:
            raise ValueError("trace interval must be positive")
        self.policy = policy
        self.every = int(every)
        self.step = 0
        with h5py.File(dataset.resolve(), "r") as source:
            demos = sorted(
                source["data"].keys(),
                key=lambda name: int(name.rsplit("_", 1)[-1]),
            )
            if not demos:
                raise RuntimeError(f"trace dataset has no demos: {dataset}")
            demo = source["data"][demos[0]]
            self.teacher_actions = np.asarray(demo["actions"])
            self.teacher_right = np.asarray(demo["obs"]["robot0_right_eef_pos"])
            self.teacher_left = np.asarray(demo["obs"]["robot0_left_eef_pos"])

    def start_episode(self):
        self.step = 0
        if hasattr(self.policy, "start_episode"):
            self.policy.start_episode()

    @staticmethod
    def _latest(ob, key: str) -> np.ndarray:
        value = np.asarray(ob[key], dtype=float)
        return value.reshape(-1, value.shape[-1])[-1]

    def __call__(self, ob):
        action = np.asarray(self.policy(ob=ob), dtype=float).reshape(-1)
        index = min(self.step, self.teacher_actions.shape[0] - 1)
        special_steps = {0, 1, 5, 10, 50, 100, 150, 200, 250, 275, 289, 298, 300, 320, 347}
        if self.step % self.every == 0 or self.step in special_steps:
            current_right = self._latest(ob, "robot0_right_eef_pos")
            current_left = self._latest(ob, "robot0_left_eef_pos")
            teacher_action = self.teacher_actions[index]
            print(
                "POLICY_TEACHER_TRACE="
                + json.dumps(
                    {
                        "step": self.step,
                        "right_eef_error_norm": float(
                            np.linalg.norm(current_right - self.teacher_right[index])
                        ),
                        "left_eef_error_norm": float(
                            np.linalg.norm(current_left - self.teacher_left[index])
                        ),
                        "current_right_eef": current_right.round(6).tolist(),
                        "teacher_right_eef": self.teacher_right[index].round(6).tolist(),
                        "current_left_eef": current_left.round(6).tolist(),
                        "teacher_left_eef": self.teacher_left[index].round(6).tolist(),
                        "action_mean_abs_error": float(
                            np.mean(np.abs(action - teacher_action))
                        ),
                        "policy_arm_action": action[:12].round(6).tolist(),
                        "teacher_arm_action": teacher_action[:12].round(6).tolist(),
                        "policy_gripper_action": action[18:20].round(6).tolist(),
                        "teacher_gripper_action": teacher_action[18:20].round(6).tolist(),
                    },
                    ensure_ascii=False,
                )
            )
        self.step += 1
        return action


def load_preclose_orientation_targets(dataset: Path) -> dict[str, np.ndarray]:
    with h5py.File(dataset, "r") as source:
        demo_key = sorted(source["data"].keys())[0]
        demo = source["data"][demo_key]
        actions = np.asarray(demo["actions"])
        closing = np.flatnonzero((actions[:, 18] > 0.0) & (actions[:, 19] > 0.0))
        if closing.size == 0:
            raise RuntimeError(f"No dual-gripper close phase found in {dataset}")
        sample = max(int(closing[0]) - 1, 0)
        targets = {
            arm: T.quat2mat(
                np.asarray(demo["obs"][f"robot0_{arm}_eef_quat"][sample])
            )
            for arm in scripted_grasp.ARMS
        }
    print(
        "BC_FINAL_SERVO_ORIENTATION_REFERENCE="
        + json.dumps(
            {
                "dataset": str(dataset.resolve()),
                "demo": demo_key,
                "preclose_step": sample,
            },
            ensure_ascii=False,
        )
    )
    return targets


def run_final_servo_rescue(
    env,
    object_name: str,
    orientation_targets: dict[str, np.ndarray] | None = None,
) -> dict:
    """Complete the last short grasp approach from live MuJoCo geometry."""
    raw_env = base_robosuite_env(env)
    robot = raw_env.robots[0]
    targets, _ = _approach_aligned_target_positions(
        raw_env,
        object_name,
        site_below_offset=0.035,
    )
    max_action = 0.3 if orientation_targets is not None else 0.65
    settle_steps = 300 if orientation_targets is not None else 200
    arrival_tolerance = 0.008
    desired_eef_targets = None
    if orientation_targets is not None:
        robot.composite_controller.update_state()
        desired_eef_targets = {}
        for arm in scripted_grasp.ARMS:
            current_orientation = np.asarray(
                robot.part_controllers[arm].ref_ori_mat,
                dtype=float,
            )
            current_offset_world = (
                scripted_grasp.gripper_end_center_pos(raw_env, robot, arm)
                - scripted_grasp.get_eef_pos(raw_env, robot, arm)
            )
            local_end_offset = current_orientation.T @ current_offset_world
            desired_eef_targets[arm] = (
                targets[arm]
                - orientation_targets[arm] @ local_end_offset
            )
    distances = {
        arm: float(
            np.linalg.norm(
                scripted_grasp.gripper_end_center_pos(raw_env, robot, arm)
                - targets[arm]
            )
        )
        for arm in scripted_grasp.ARMS
    }
    orientation_errors = {arm: float("inf") for arm in scripted_grasp.ARMS}
    for _ in range(settle_steps):
        position_ready = all(
            distance <= arrival_tolerance for distance in distances.values()
        )
        orientation_ready = orientation_targets is None or all(
            error <= 0.05 for error in orientation_errors.values()
        )
        if position_ready and orientation_ready:
            break
        robot.composite_controller.update_state()
        arm_actions = {}
        for arm in scripted_grasp.ARMS:
            if desired_eef_targets is None:
                world_delta = (
                    targets[arm]
                    - scripted_grasp.gripper_end_center_pos(raw_env, robot, arm)
                )
            else:
                world_delta = (
                    desired_eef_targets[arm]
                    - scripted_grasp.get_eef_pos(raw_env, robot, arm)
                )
            controller_delta = scripted_grasp.world_delta_to_controller_frame(
                robot,
                arm,
                world_delta,
            )
            arm_action = scripted_grasp.arm_delta_to_normalized_action(
                robot=robot,
                arm=arm,
                delta_pos=controller_delta,
                max_action=max_action,
            )
            if orientation_targets is not None:
                controller = robot.part_controllers[arm]
                current_world = np.asarray(controller.ref_ori_mat, dtype=float)
                if controller.input_ref_frame == "base":
                    origin_ori = controller.origin_ori
                    if origin_ori is None:
                        _, origin_ori = robot.composite_controller.get_controller_base_pose(
                            controller_name=arm
                        )
                    desired = origin_ori.T @ orientation_targets[arm]
                    current = origin_ori.T @ current_world
                else:
                    desired = orientation_targets[arm]
                    current = current_world
                rotation_delta = T.quat2axisangle(
                    T.mat2quat(desired @ current.T)
                )
                rotation_scale = np.maximum(
                    np.abs(controller.output_min[3:6]),
                    np.abs(controller.output_max[3:6]),
                )
                arm_action[3:6] = np.clip(
                    np.divide(
                        rotation_delta,
                        rotation_scale,
                        out=np.zeros(3),
                        where=rotation_scale > 0,
                    ),
                    -min(max_action, 0.2),
                    min(max_action, 0.2),
                )
                orientation_errors[arm] = float(np.linalg.norm(rotation_delta))
            arm_actions[arm] = arm_action
        action = scripted_grasp.build_action(
            raw_env,
            robot,
            arm_actions,
            gripper_value=-1.0,
        )
        env.step(action)
        distances = {
            arm: float(
                np.linalg.norm(
                    scripted_grasp.gripper_end_center_pos(raw_env, robot, arm)
                    - targets[arm]
                )
            )
            for arm in scripted_grasp.ARMS
        }

    if orientation_targets is not None:
        robot.composite_controller.update_state()
        for arm in scripted_grasp.ARMS:
            controller = robot.part_controllers[arm]
            current_world = np.asarray(controller.ref_ori_mat, dtype=float)
            if controller.input_ref_frame == "base":
                origin_ori = controller.origin_ori
                if origin_ori is None:
                    _, origin_ori = robot.composite_controller.get_controller_base_pose(
                        controller_name=arm
                    )
                desired = origin_ori.T @ orientation_targets[arm]
                current = origin_ori.T @ current_world
            else:
                desired = orientation_targets[arm]
                current = current_world
            orientation_errors[arm] = float(
                np.linalg.norm(
                    T.quat2axisangle(T.mat2quat(desired @ current.T))
                )
            )

    ok = all(distance <= arrival_tolerance for distance in distances.values())
    if orientation_targets is not None:
        ok = ok and all(error <= 0.05 for error in orientation_errors.values())
    reason = "" if ok else f"final servo target tolerance failed: {distances}"
    print(
        "BC final live-target servo before grasp: "
        f"distances={distances}, orientation_errors={orientation_errors}"
    )
    if not ok:
        print(f"BC_FINAL_SERVO_RESULT={json.dumps({'success': False, 'reason': reason})}")
        return {
            "success": False,
            "successes": 0,
            "num_rollouts": 1,
            "return": 0.0,
            "rescue_reason": reason,
        }

    zero_arm_actions = {
        arm: np.zeros(6, dtype=float) for arm in scripted_grasp.ARMS
    }
    close_action = scripted_grasp.build_action(
        raw_env,
        robot,
        zero_arm_actions,
        gripper_value=1.0,
    )
    for _ in range(40):
        env.step(close_action)
    for _ in range(10):
        env.step(close_action)
    grasps = scripted_grasp.grasp_status(raw_env, robot, object_name)
    success = all(grasps.values())
    print(
        "BC_FINAL_SERVO_RESULT="
        + json.dumps(
            {
                "success": success,
                "targets": {
                    arm: np.asarray(target).round(6).tolist()
                    for arm, target in targets.items()
                },
                "grasp_status": grasps,
            },
            ensure_ascii=False,
        )
    )
    return {
        "success": success,
        "successes": int(success),
        "num_rollouts": 1,
        "return": 0.0,
        "rescue": True,
    }


def run_scripted_grasp_fallback(env, object_name: str) -> dict:
    """Run the exact online scripted skill, including its timing profile."""
    from robot_agent.skills.grasp_fallback import run_dynamic_scripted_grasp

    return run_dynamic_scripted_grasp(
        env=env,
        object_name=object_name,
        render=False,
    )


def make_policy_args(
    args: argparse.Namespace,
    spec: dict,
    grasp_params: dict,
) -> argparse.Namespace:
    return argparse.Namespace(
        checkpoint=args.checkpoint.resolve(),
        factory_scene=spec["environment"],
        object_name=spec["object_name"],
        robot_base_pos=spec["robot_base_pos"],
        robot_base_ori=spec["robot_base_ori"],
        num_rollouts=1,
        eval_steps=int(grasp_params["eval_steps"]),
        device=args.device,
        debug_policy=bool(grasp_params.get("debug_policy", False)),
        debug_every=int(grasp_params.get("debug_every", 25)),
        verbose=False,
        site_below_offset=0.035,
        post_hold_steps=int(grasp_params["post_hold_steps"]),
        initial_view_steps=int(grasp_params["initial_view_steps"]),
        render_sleep=0.0,
        camera_height=128,
        camera_width=128,
        show_object_sites=False,
        object_site_size=0.04,
        renderer="mjviewer",
        camera="robot0_robotview",
        controller=None,
        gripper_types="Robotiq140Gripper",
        seed=args.policy_seed,
        no_render=True,
        save_grasp_init_state=None,
    )


def print_policy_initial_state(env, *, init_mode: str) -> None:
    raw_env = base_robosuite_env(env)
    robot = raw_env.robots[0]
    joint_names = (
        "robot0_torso_lift_joint",
        "robot0_arm_right_1_joint",
        "robot0_arm_right_3_joint",
        "robot0_arm_right_4_joint",
        "robot0_arm_left_1_joint",
        "robot0_arm_left_3_joint",
        "robot0_arm_left_4_joint",
        "gripper0_right_finger_joint",
        "gripper0_left_finger_joint",
    )
    joints = {}
    for joint_name in joint_names:
        try:
            joints[joint_name] = float(
                raw_env.sim.data.qpos[
                    raw_env.sim.model.joint_name2id(joint_name)
                ]
            )
        except Exception:
            continue
    eef = {
        arm: gripper_end_center_pos(raw_env, robot, arm).tolist()
        for arm in ("right", "left")
    }
    print(
        "POLICY_INITIAL_STATE="
        + json.dumps(
            {
                "init_mode": init_mode,
                "joints": joints,
                "gripper_end_positions": eef,
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    args = parse_args()
    spec = resolve_collection_spec(args)
    alignment_args = argparse.Namespace(
        **vars(args),
        controller=None,
        gripper_types="Robotiq140Gripper",
        renderer="mjviewer",
        camera="robot0_robotview",
        camera_height=128,
        camera_width=128,
    )
    _apply_live_object_alignment(alignment_args, spec)
    params = load_robot_params()
    grasp_params = dict(params["grasp_policy"])
    if args.eval_steps is not None:
        grasp_params["eval_steps"] = int(args.eval_steps)
    lift_params = params["lift"]
    policy_args = make_policy_args(args, spec, grasp_params)

    print(
        json.dumps(
            {
                "checkpoint": str(policy_args.checkpoint),
                "level": spec["level"],
                "environment": spec["environment"],
                "object_name": spec["object_name"],
                "robot_base_pos": spec["robot_base_pos"],
                "robot_base_ori": spec["robot_base_ori"],
                "coordinate_authority": spec["coordinate_authority"],
                "grasp_params": {
                    "eval_steps": policy_args.eval_steps,
                    "post_hold_steps": policy_args.post_hold_steps,
                    "initial_view_steps": policy_args.initial_view_steps,
                },
                "lift_params": lift_params,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    policy, config, checkpoint_dict = load_policy_and_config(policy_args)
    if args.arm_action_slew_limit is not None:
        policy = ArmActionSlewLimiter(policy, args.arm_action_slew_limit)
        print(f"Arm action slew limit: {args.arm_action_slew_limit:.6f}")
    if args.arm_translation_ema_alpha is not None:
        policy = ArmTranslationEmaPolicy(
            policy,
            args.arm_translation_ema_alpha,
        )
        print(
            "Arm translation EMA alpha: "
            f"{args.arm_translation_ema_alpha:.6f}"
        )
    if args.zero_arm_rotation_actions:
        policy = ZeroArmRotationPolicy(policy)
        print("Dual-arm OSC rotation actions constrained to zero")
    skill_context = None
    active_evaluation = None
    if args.apply_skill_initializer:
        from robot_agent.skills.pick_up import (
            _scripted_first_with_bc_recovery_enabled,
            _standardized_grasp_env_initialization,
        )

        skill_context = _standardized_grasp_env_initialization(
            scripted_first_with_bc_recovery=(
                _scripted_first_with_bc_recovery_enabled()
            ),
        )
        skill_context.__enter__()
        from robosuite.environments.factory_sorting import (
            load_factory_sorting_evalization as active_evaluation,
        )

        env = active_evaluation.make_eval_env(
            policy_args,
            config=config,
            ckpt_dict=checkpoint_dict,
            render=False,
        )
    else:
        env = make_eval_env(
            policy_args,
            config=config,
            ckpt_dict=checkpoint_dict,
            render=False,
        )

    original_initial_obs_reader = None
    try:
        initial_policy_obs = None
        if args.init_mode in {"reset", "reset_to"}:
            initial_policy_obs = env.reset()
        if args.init_mode == "reset_to":
            state = env.get_state()
            initial_policy_obs = env.reset_to(state)
        if args.direct_initial_observation:
            from robosuite.environments.factory_sorting import (
                load_factory_sorting_evalization as evaluation_module,
            )

            original_initial_obs_reader = (
                evaluation_module.current_wrapped_policy_obs
            )

            def direct_initial_obs(wrapped_env):
                obs = initial_policy_obs
                if obs is None:
                    raise RuntimeError(
                        "wrapped environment reset returned no direct observation"
                    )
                return obs

            evaluation_module.current_wrapped_policy_obs = direct_initial_obs
            print("Initial observation mode: direct post-reset observation")
        print_policy_initial_state(env, init_mode=args.init_mode)
        if args.trace_dataset is not None:
            policy = TeacherTracePolicy(
                policy=policy,
                dataset=args.trace_dataset,
                every=args.trace_every,
            )

        if args.scripted_grasp_only:
            grasp_result = {
                "success": False,
                "reason": "BC rollout skipped for scripted-path validation",
            }
        else:
            grasp_runner = (
                active_evaluation.run_factory_sorting_grasp_in_wrapped_env
                if active_evaluation is not None
                else run_factory_sorting_grasp_in_wrapped_env
            )
            grasp_result = grasp_runner(
                env=env,
                policy=policy,
                object_name=spec["object_name"],
                eval_steps=policy_args.eval_steps,
                post_hold_steps=policy_args.post_hold_steps,
                initial_view_steps=policy_args.initial_view_steps,
                camera=policy_args.camera,
                render=False,
            )
        if args.rescue_final_servo and not grasp_result.get("success"):
            orientation_targets = None
            if args.rescue_orientation_dataset is not None:
                orientation_targets = load_preclose_orientation_targets(
                    args.rescue_orientation_dataset
                )
            grasp_result = run_final_servo_rescue(
                env=env,
                object_name=spec["object_name"],
                orientation_targets=orientation_targets,
            )
        if args.fallback_scripted_grasp and not grasp_result.get("success"):
            grasp_result = run_scripted_grasp_fallback(
                env=env,
                object_name=spec["object_name"],
            )
        lift_result = lift_grasped_object(
            env=env,
            object_name=spec["object_name"],
            lift_height=float(lift_params["lift_height"]),
            max_steps=int(lift_params["max_steps"]),
            hold_steps=int(lift_params["hold_steps"]),
            tolerance=float(lift_params["tolerance"]),
            max_action=float(lift_params["max_action"]),
            render=False,
        )
        passed = bool(grasp_result.get("success")) and bool(
            lift_result.get("success")
        )
        print(
            "GRASP_LIFT_GATE_RESULT="
            + json.dumps(
                {
                    "passed": passed,
                    "grasp": grasp_result,
                    "lift": lift_result,
                },
                ensure_ascii=False,
            )
        )
        return 0 if passed else 1
    finally:
        if original_initial_obs_reader is not None:
            evaluation_module.current_wrapped_policy_obs = (
                original_initial_obs_reader
            )
        if hasattr(env, "close"):
            env.close()
        if skill_context is not None:
            skill_context.__exit__(None, None, None)
        gc.collect()


if __name__ == "__main__":
    raise SystemExit(main())
