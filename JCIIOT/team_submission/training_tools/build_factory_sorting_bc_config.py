"""Build a formal BC training config from the organizer's reference checkpoint.

This deliberately reuses the complete config embedded in model_epoch_150.pth
instead of maintaining a second, hand-written copy of the architecture and
observation settings.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE = (
    PROJECT_ROOT / "robosuite" / "robosuite" / "model_epoch_150.pth"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "team_submission" / "training_outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Prepared training HDF5.")
    parser.add_argument("--output", required=True, help="Config JSON to create.")
    parser.add_argument(
        "--reference-checkpoint",
        default=str(DEFAULT_REFERENCE),
        help="Organizer checkpoint whose embedded config is used as the template.",
    )
    parser.add_argument("--name", default="factory_sorting_l2_bc")
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--resume-checkpoint",
        default="",
        help="Optional robomimic checkpoint to resume from.",
    )
    parser.add_argument(
        "--action-normalization",
        choices=("none", "min_max", "gaussian"),
        default="none",
        help="Robomimic action normalization applied independently per action dimension.",
    )
    parser.add_argument(
        "--include-timesteps",
        action="store_true",
        help="Include the online timesteps observation as a low-dimensional input.",
    )
    parser.add_argument(
        "--exclude-rgb",
        action="store_true",
        help=(
            "Train a low-dimensional policy without RGB observations. This is "
            "intended for a dedicated single-object checkpoint whose trajectory "
            "is identified outside the policy."
        ),
    )
    parser.add_argument(
        "--loss",
        choices=("l2", "l1"),
        default="l2",
        help="Behavior-cloning action loss.",
    )
    return parser.parse_args()


def inspect_dataset(path: Path) -> tuple[int, list[str], int]:
    with h5py.File(path, "r") as source:
        if "data" not in source:
            raise RuntimeError(f"{path} has no /data group")
        demos = sorted(name for name in source["data"] if name.startswith("demo_"))
        if not demos:
            raise RuntimeError(f"{path} contains no demonstrations")
        first = source["data"][demos[0]]
        obs_keys = sorted(first["obs"].keys())
        action_dim = int(first["actions"].shape[-1])
        return len(demos), obs_keys, action_dim


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset).resolve()
    output = Path(args.output).resolve()
    reference = Path(args.reference_checkpoint).resolve()
    resume_checkpoint = (
        Path(args.resume_checkpoint).resolve() if args.resume_checkpoint else None
    )

    if not dataset.is_file():
        raise FileNotFoundError(dataset)
    if not reference.is_file():
        raise FileNotFoundError(reference)
    if resume_checkpoint is not None and not resume_checkpoint.is_file():
        raise FileNotFoundError(resume_checkpoint)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing config: {output}")
    if args.epochs <= 0:
        raise ValueError("--epochs must be positive")

    num_demos, obs_keys, action_dim = inspect_dataset(dataset)
    if action_dim != 20:
        raise RuntimeError(f"expected 20-dimensional actions, got {action_dim}")

    checkpoint = torch.load(reference, map_location="cpu", weights_only=False)
    config = json.loads(checkpoint["config"])

    # The supplied checkpoint was written by an older robomimic config schema.
    # These values now live at experiment.epoch_every_n_steps and
    # train.num_epochs; leaving the legacy duplicates in place makes the
    # current key-locked config loader reject the JSON.
    policy_optim = config["algo"]["optim_params"]["policy"]
    policy_optim.pop("num_train_batches", None)
    policy_optim.pop("num_epochs", None)

    required_low_dim = config["observation"]["modalities"]["obs"]["low_dim"]
    required_rgb = config["observation"]["modalities"]["obs"]["rgb"]
    if args.exclude_rgb:
        required_rgb.clear()
    if args.include_timesteps:
        if "timesteps" not in obs_keys:
            raise RuntimeError("--include-timesteps requires obs/timesteps in HDF5")
        if "timesteps" not in required_low_dim:
            required_low_dim.append("timesteps")
    missing_obs = sorted(set(required_low_dim + required_rgb).difference(obs_keys))
    if missing_obs:
        raise RuntimeError(f"dataset is missing required observations: {missing_obs}")

    # Keep the reference architecture, modalities, optimizer, frame stack, and
    # checkpoint interval. Only bind the new data and run-specific locations.
    config["experiment"]["name"] = args.name
    config["experiment"]["validate"] = False
    config["experiment"]["rollout"]["enabled"] = False
    config["experiment"]["render"] = False
    config["experiment"]["render_video"] = False
    config["experiment"]["ckpt_path"] = (
        str(resume_checkpoint) if resume_checkpoint is not None else None
    )
    config["train"]["data"] = [{"path": str(dataset)}]
    config["train"]["output_dir"] = str(DEFAULT_OUTPUT_DIR.resolve())
    config["train"]["cuda"] = True
    config["train"]["num_epochs"] = args.epochs
    config["train"]["seed"] = args.seed
    config["train"]["hdf5_cache_mode"] = "low_dim"
    config["train"]["action_config"]["actions"]["normalization"] = (
        None if args.action_normalization == "none" else args.action_normalization
    )
    config["algo"]["loss"]["l2_weight"] = 1.0 if args.loss == "l2" else 0.0
    config["algo"]["loss"]["l1_weight"] = 1.0 if args.loss == "l1" else 0.0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "config": str(output),
                "reference_checkpoint": str(reference),
                "dataset": str(dataset),
                "num_demos": num_demos,
                "action_dim": action_dim,
                "epochs": args.epochs,
                "action_normalization": args.action_normalization,
                "resume_checkpoint": (
                    str(resume_checkpoint) if resume_checkpoint is not None else None
                ),
                "include_timesteps": args.include_timesteps,
                "exclude_rgb": args.exclude_rgb,
                "loss": args.loss,
                "cuda": config["train"]["cuda"],
                "rollout_during_training": config["experiment"]["rollout"]["enabled"],
                "training_output_dir": config["train"]["output_dir"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
