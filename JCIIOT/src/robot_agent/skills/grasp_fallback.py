"""Skill-layer grasp fallback built from the successful demonstration controller.

This adapter deliberately changes no organizer-owned environment or controller
file. It temporarily reuses their public scripted-control helpers against the
already-created grasp environment and restores every patched symbol afterward.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _scripted_motion_step_scale() -> float:
    """Read the archived scripted-grasp timing scale from player config."""
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    data = json.loads(params_path.read_text(encoding="utf-8"))
    value = float(
        data.get("grasp_policy", {}).get(
            "scripted_motion_step_scale",
            1.0,
        )
    )
    if not 0.50 <= value <= 1.50:
        raise ValueError(
            "grasp_policy.scripted_motion_step_scale must be in [0.50, 1.50]"
        )
    return value


def sync_material_object_states(source_env, destination_env) -> int:
    """Copy material object qpos/qvel while leaving the robot state untouched."""
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
    render: bool = False,
    nav_env=None,
) -> dict:
    """Reset the temporary grasp env and grasp from live object geometry."""
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

    def reset_with_current_scene(*args, **kwargs):
        observation = original_reset(*args, **kwargs)
        if nav_env is not None:
            copied = sync_material_object_states(nav_env, raw_env)
            print(
                f"SKILL_GRASP_FALLBACK_SCENE_SYNC copied_objects={copied}",
                flush=True,
            )
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

    result = {
        "success": bool(success),
        "successes": int(bool(success)),
        "num_rollouts": 1,
        "return": float(bool(success)),
        "scripted_fallback": True,
        "reason": reason,
        "motion_step_scale": motion_scale,
        "motion_steps": {
            "up": args.up_steps,
            "xy": args.xy_steps,
            "down": args.down_steps,
            "settle": args.settle_steps,
            "grasp": args.grasp_steps,
            "post_success_hold": args.post_success_hold_steps,
        },
    }
    print(
        "SKILL_GRASP_FALLBACK_RESULT="
        + json.dumps(result, ensure_ascii=False),
        flush=True,
    )
    return result
