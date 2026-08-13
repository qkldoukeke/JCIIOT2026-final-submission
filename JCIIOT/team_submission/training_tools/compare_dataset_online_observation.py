"""Compare a prepared HDF5 observation with the matching online observation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import h5py
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
for path in (PROJECT_ROOT, PROJECT_ROOT / "robosuite", PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from collect_factory_sorting import (  # noqa: E402
    _apply_live_object_alignment,
    resolve_collection_spec,
)
from robot_agent.skills.pick_up import (  # noqa: E402
    _standardized_grasp_env_initialization,
)
from validate_grasp_lift_checkpoint import (  # noqa: E402
    load_robot_params,
    make_policy_args,
)
from robosuite.environments.factory_sorting import (  # noqa: E402
    load_factory_sorting_evalization as active_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--level", required=True)
    parser.add_argument("--object-index", type=int, default=0)
    parser.add_argument("--environment", default="")
    parser.add_argument("--seed", type=int, default=15780)
    parser.add_argument("--policy-seed", type=int, default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--full-demo-action-report", action="store_true")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--timestep-probe-steps", type=int, default=0)
    return parser.parse_args()


def digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()[:16]


def array_report(dataset_value: np.ndarray, online_value: np.ndarray) -> dict:
    left = np.asarray(dataset_value)
    right = np.asarray(online_value)
    report = {
        "dataset_shape": list(left.shape),
        "online_shape": list(right.shape),
        "dataset_dtype": str(left.dtype),
        "online_dtype": str(right.dtype),
        "dataset_min": float(np.min(left)),
        "dataset_max": float(np.max(left)),
        "online_min": float(np.min(right)),
        "online_max": float(np.max(right)),
        "dataset_sha256": digest(left),
        "online_sha256": digest(right),
    }
    if left.shape == right.shape:
        difference = left.astype(np.float64) - right.astype(np.float64)
        report["mean_abs_error"] = float(np.mean(np.abs(difference)))
        report["max_abs_error"] = float(np.max(np.abs(difference)))
        if left.ndim >= 3:
            flipped = left[::-1, ...].astype(np.float64) - right.astype(np.float64)
            report["vertical_flip_mean_abs_error"] = float(
                np.mean(np.abs(flipped))
            )
            report["vertical_flip_max_abs_error"] = float(
                np.max(np.abs(flipped))
            )
    elif right.ndim == left.ndim + 1 and right.shape[1:] == left.shape:
        difference = right.astype(np.float64) - left.astype(np.float64)[None, ...]
        report["online_frame_count"] = int(right.shape[0])
        report["all_frames_mean_abs_error"] = float(np.mean(np.abs(difference)))
        report["all_frames_max_abs_error"] = float(np.max(np.abs(difference)))
        report["latest_frame_mean_abs_error"] = float(
            np.mean(np.abs(difference[-1]))
        )
        report["latest_frame_max_abs_error"] = float(
            np.max(np.abs(difference[-1]))
        )
        if left.ndim >= 3:
            latest_flipped = (
                right[-1].astype(np.float64)
                - left[::-1, ...].astype(np.float64)
            )
            report["latest_frame_vertical_flip_mean_abs_error"] = float(
                np.mean(np.abs(latest_flipped))
            )
            report["latest_frame_vertical_flip_max_abs_error"] = float(
                np.max(np.abs(latest_flipped))
            )
    return report


def main() -> None:
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
    policy_args = make_policy_args(args, spec, dict(params["grasp_policy"]))
    policy, config, checkpoint_dict = active_evaluation.load_policy_and_config(
        policy_args
    )

    with _standardized_grasp_env_initialization():
        env = active_evaluation.make_eval_env(
            policy_args,
            config=config,
            ckpt_dict=checkpoint_dict,
            render=False,
        )

    try:
        env.reset()
        state = env.get_state()
        online_obs = env.reset_to(state)
        if online_obs is None:
            online_obs = env.get_observation()

        with h5py.File(args.dataset.resolve(), "r") as source:
            demo_group = source["data"]["demo_1"]
            demo = demo_group["obs"]
            required = (
                list(config.observation.modalities.obs.low_dim)
                + list(config.observation.modalities.obs.rgb)
            )
            report = {
                "object_name": spec["object_name"],
                "robot_base_pos": spec["robot_base_pos"],
                "robot_base_ori": spec["robot_base_ori"],
                "fields": {},
                "auxiliary_fields": {},
                "dataset_observation_keys": sorted(demo.keys()),
                "online_observation_keys": sorted(online_obs.keys()),
            }
            for key in required:
                report["fields"][key] = array_report(
                    np.asarray(demo[key][0]),
                    np.asarray(online_obs[key]),
                )
            for key in ("timesteps",):
                if key in demo and key in online_obs:
                    report["auxiliary_fields"][key] = array_report(
                        np.asarray(demo[key][0]),
                        np.asarray(online_obs[key]),
                    )
            if hasattr(policy, "start_episode"):
                policy.start_episode()
            teacher_action = np.asarray(demo_group["actions"][0], dtype=np.float64)
            predicted_action = np.asarray(
                policy(ob=online_obs), dtype=np.float64
            ).reshape(-1)
            action_difference = predicted_action - teacher_action
            report["initial_action"] = {
                "teacher": teacher_action.tolist(),
                "predicted": predicted_action.tolist(),
                "mean_abs_error": float(np.mean(np.abs(action_difference))),
                "max_abs_error": float(np.max(np.abs(action_difference))),
                "l2_error": float(np.linalg.norm(action_difference)),
            }
            if args.full_demo_action_report:
                if hasattr(policy, "start_episode"):
                    policy.start_episode()
                teacher_actions = np.asarray(
                    demo_group["actions"], dtype=np.float64
                )
                demo_arrays = {
                    key: np.asarray(demo[key]) for key in required
                }
                predictions = []
                context_length = int(config.train.frame_stack)
                for timestep in range(teacher_actions.shape[0]):
                    start = max(0, timestep - context_length + 1)
                    indices = list(range(start, timestep + 1))
                    indices = [indices[0]] * (context_length - len(indices)) + indices
                    stacked_obs = {
                        key: demo_arrays[key][indices] for key in required
                    }
                    predictions.append(
                        np.asarray(policy(ob=stacked_obs), dtype=np.float64).reshape(-1)
                    )
                predicted_actions = np.stack(predictions)
                absolute_error = np.abs(predicted_actions - teacher_actions)
                ranges = (
                    (0, 10),
                    (10, 50),
                    (50, 100),
                    (100, 150),
                    (150, 200),
                    (200, 250),
                    (250, 300),
                    (300, teacher_actions.shape[0]),
                )
                report["full_demo_action_report"] = {
                    "overall_mean_abs_error": float(np.mean(absolute_error)),
                    "overall_max_abs_error": float(np.max(absolute_error)),
                    "mean_abs_error_by_dimension": np.mean(
                        absolute_error, axis=0
                    ).tolist(),
                    "ranges": [
                        {
                            "start": start,
                            "end": end,
                            "mean_abs_error": float(
                                np.mean(absolute_error[start:end])
                            ),
                            "max_abs_error": float(
                                np.max(absolute_error[start:end])
                            ),
                        }
                        for start, end in ranges
                        if start < end
                    ],
                    "selected_steps": {
                        str(timestep): {
                            "teacher": teacher_actions[timestep].tolist(),
                            "predicted": predicted_actions[timestep].tolist(),
                            "mean_abs_error": float(
                                np.mean(absolute_error[timestep])
                            ),
                        }
                        for timestep in (0, 1, 5, 10, 50, 100, 150, 200, 250, 300, 347)
                    },
                }
            if args.timestep_probe_steps > 0 and "timesteps" in online_obs:
                timestep_probe = [np.asarray(online_obs["timesteps"]).tolist()]
                for _ in range(args.timestep_probe_steps):
                    step_result = env.step(np.zeros(20, dtype=np.float32))
                    probe_obs = step_result[0]
                    timestep_probe.append(
                        np.asarray(probe_obs["timesteps"]).tolist()
                    )
                report["timestep_probe"] = timestep_probe
        if args.compact:
            initial_teacher = np.asarray(report["initial_action"]["teacher"])
            initial_predicted = np.asarray(report["initial_action"]["predicted"])
            initial_absolute_error = np.abs(initial_predicted - initial_teacher)
            initial_max_dimension = int(np.argmax(initial_absolute_error))
            compact_report = {
                "initial_action": {
                    key: report["initial_action"][key]
                    for key in ("mean_abs_error", "max_abs_error", "l2_error")
                },
                "observation_max_abs_error": {
                    key: values.get(
                        "max_abs_error", values.get("all_frames_max_abs_error")
                    )
                    for key, values in report["fields"].items()
                },
                "observation_alignment": {
                    key: {
                        metric: values[metric]
                        for metric in (
                            "mean_abs_error",
                            "max_abs_error",
                            "latest_frame_mean_abs_error",
                            "latest_frame_max_abs_error",
                            "vertical_flip_mean_abs_error",
                            "vertical_flip_max_abs_error",
                            "latest_frame_vertical_flip_mean_abs_error",
                            "latest_frame_vertical_flip_max_abs_error",
                        )
                        if metric in values
                    }
                    for key, values in report["fields"].items()
                },
                "auxiliary_fields": report["auxiliary_fields"],
                "dataset_observation_keys": report["dataset_observation_keys"],
                "online_observation_keys": report["online_observation_keys"],
                "online_timestep": (
                    {
                        "shape": list(np.asarray(online_obs["timesteps"]).shape),
                        "value": np.asarray(online_obs["timesteps"]).tolist(),
                    }
                    if "timesteps" in online_obs
                    else None
                ),
                "timestep_probe": report.get("timestep_probe"),
            }
            compact_report["initial_action"].update(
                {
                    "max_error_dimension": initial_max_dimension,
                    "teacher_at_max": float(initial_teacher[initial_max_dimension]),
                    "predicted_at_max": float(
                        initial_predicted[initial_max_dimension]
                    ),
                    "teacher": initial_teacher.tolist(),
                    "predicted": initial_predicted.tolist(),
                }
            )
            if "full_demo_action_report" in report:
                full_report = report["full_demo_action_report"]
                compact_report.update(
                    {
                        "overall_mean_abs_error": full_report[
                            "overall_mean_abs_error"
                        ],
                        "overall_max_abs_error": full_report[
                            "overall_max_abs_error"
                        ],
                        "mean_abs_error_by_dimension": full_report[
                            "mean_abs_error_by_dimension"
                        ],
                        "ranges": full_report["ranges"],
                        "selected_step_mean_abs_error": {
                            timestep: values["mean_abs_error"]
                            for timestep, values in full_report[
                                "selected_steps"
                            ].items()
                        },
                    }
                )
            print("FULL_DEMO_ACTION_SUMMARY=" + json.dumps(compact_report))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        if hasattr(env, "close"):
            env.close()


if __name__ == "__main__":
    main()
