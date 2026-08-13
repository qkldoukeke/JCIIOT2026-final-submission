"""Build a robomimic-ready training dataset without changing collected HDF5 files.

The factory collectors cache raw robosuite camera observations. MuJoCo camera
images are vertically inverted, while robomimic's online EnvRobosuite wrapper
returns vertically corrected images. This tool merges one or more successful
collector datasets and flips only RGB / depth observations along image height.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

import h5py
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Collected HDF5 path. Repeat this option to merge multiple files.",
    )
    parser.add_argument("--output", required=True, help="New training HDF5 path.")
    parser.add_argument(
        "--add-online-timesteps",
        action="store_true",
        help=(
            "Add obs/timesteps using the verified online convention: "
            "action index t observes max(t - 1, 0)."
        ),
    )
    return parser.parse_args()


def copy_attrs(source, destination) -> None:
    for key, value in source.attrs.items():
        destination.attrs[key] = value


def copy_dataset(source: h5py.Dataset, parent: h5py.Group, name: str) -> None:
    destination = parent.create_dataset(name, data=source[()])
    copy_attrs(source, destination)


def copy_observation(
    source: h5py.Dataset,
    parent: h5py.Group,
    name: str,
) -> None:
    is_visual = name.endswith("_image") or name.endswith("_depth")
    if is_visual:
        if source.ndim < 3:
            raise RuntimeError(
                f"visual observation {source.name} has invalid shape {source.shape}"
            )
        # Shape is (T, H, W, C), so axis 1 is image height.
        # h5py does not support negative-stride selections, so load one
        # demonstration observation array and then flip it in NumPy.
        values = source[()][:, ::-1, ...]
        destination = parent.create_dataset(
            name,
            data=values,
            compression="gzip",
            compression_opts=4,
        )
    else:
        destination = parent.create_dataset(name, data=source[()])
    copy_attrs(source, destination)


def ordered_demo_names(data: h5py.Group) -> list[str]:
    names = [name for name in data.keys() if name.startswith("demo_")]
    return sorted(names, key=lambda name: int(name.rsplit("_", 1)[-1]))


def inspect_input(path: Path) -> dict:
    with h5py.File(path, "r") as source:
        if "data" not in source:
            raise RuntimeError(f"{path} has no /data group")
        data = source["data"]
        demos = ordered_demo_names(data)
        if not demos:
            raise RuntimeError(f"{path} contains no demo_* groups")

        first = data[demos[0]]
        required = {"actions", "states", "obs"}
        missing = sorted(required.difference(first.keys()))
        if missing:
            raise RuntimeError(f"{path}/{demos[0]} is missing {missing}")

        env_args = str(data.attrs.get("env_args", ""))
        try:
            env_signature = json.loads(env_args)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path} has invalid data.env_args JSON: {exc}") from exc
        # Different collection seeds intentionally produce different demos but
        # do not change observation, action, controller, or environment schema.
        env_kwargs_signature = env_signature.get("env_kwargs", {})
        env_kwargs_signature.pop("seed", None)
        # Multi-object collection aligns the robot base independently to each
        # live target. The resulting base pose remains present in every saved
        # simulator state and observation; it is not a schema difference.
        env_kwargs_signature.pop("robot_base_pos", None)

        return {
            "path": str(path),
            "env": str(data.attrs.get("env", "")),
            "env_args": env_args,
            "env_signature": env_signature,
            "obs_keys": sorted(first["obs"].keys()),
            "action_dim": int(first["actions"].shape[-1]),
            "num_demos": len(demos),
            "policy_info": str(data.attrs.get("policy_info", "")),
        }


def validate_compatibility(reports: list[dict]) -> None:
    reference = reports[0]
    for report in reports[1:]:
        for key in ("env", "env_signature", "obs_keys", "action_dim"):
            if report[key] != reference[key]:
                raise RuntimeError(
                    f"input datasets disagree on {key}: "
                    f"{reference['path']} != {report['path']}"
                )


def build_dataset(
    input_paths: list[Path],
    output_path: Path,
    add_online_timesteps: bool = False,
) -> dict:
    reports = [inspect_input(path) for path in input_paths]
    validate_compatibility(reports)

    if output_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing training dataset: {output_path}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".partial")
    if temporary_path.exists():
        raise FileExistsError(
            f"remove the incomplete file before retrying: {temporary_path}"
        )

    next_demo_number = 1
    image_keys: set[str] = set()
    try:
        with h5py.File(temporary_path, "w") as destination:
            destination_data = destination.create_group("data")

            with h5py.File(input_paths[0], "r") as first_source:
                copy_attrs(first_source["data"], destination_data)

            for input_path in input_paths:
                with h5py.File(input_path, "r") as source:
                    source_data = source["data"]
                    for source_demo_name in ordered_demo_names(source_data):
                        source_demo = source_data[source_demo_name]
                        destination_demo = destination_data.create_group(
                            f"demo_{next_demo_number}"
                        )
                        copy_attrs(source_demo, destination_demo)

                        for key, item in source_demo.items():
                            if key == "obs":
                                destination_obs = destination_demo.create_group("obs")
                                copy_attrs(item, destination_obs)
                                for obs_key, obs_dataset in item.items():
                                    copy_observation(
                                        obs_dataset,
                                        destination_obs,
                                        obs_key,
                                    )
                                    if obs_key.endswith(("_image", "_depth")):
                                        image_keys.add(obs_key)
                            elif isinstance(item, h5py.Dataset):
                                copy_dataset(item, destination_demo, key)
                            else:
                                raise RuntimeError(
                                    f"unsupported group {item.name} in demonstration"
                                )
                        if "actions" not in destination_demo:
                            raise RuntimeError(
                                f"{source_demo.name} has no actions dataset"
                            )
                        if add_online_timesteps:
                            destination_obs = destination_demo["obs"]
                            if "timesteps" in destination_obs:
                                raise RuntimeError(
                                    f"{source_demo.name} already contains obs/timesteps"
                                )
                            num_actions = int(destination_demo["actions"].shape[0])
                            timestep_values = np.maximum(
                                np.arange(num_actions, dtype=np.int64) - 1,
                                0,
                            ).reshape(-1, 1)
                            destination_obs.create_dataset(
                                "timesteps", data=timestep_values
                            )
                        destination_demo.attrs["num_samples"] = int(
                            destination_demo["actions"].shape[0]
                        )
                        next_demo_number += 1

            num_demos = next_demo_number - 1
            destination_data.attrs["num_successful_demos"] = num_demos
            destination_data.attrs["training_data_preparation"] = json.dumps(
                {
                    "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "source_datasets": reports,
                    "transform": (
                        "vertical_flip_visual_observations+online_timesteps"
                        if add_online_timesteps
                        else "vertical_flip_visual_observations"
                    ),
                    "visual_keys": sorted(image_keys),
                },
                ensure_ascii=False,
            )
            destination.flush()

        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    return {
        "status": "PASS",
        "output": str(output_path),
        "num_demos": next_demo_number - 1,
        "source_num_demos": sum(report["num_demos"] for report in reports),
        "visual_keys_flipped": sorted(image_keys),
        "online_timesteps_added": add_online_timesteps,
        "original_files_modified": False,
    }


def main() -> None:
    args = parse_args()
    input_paths = [Path(value).expanduser().resolve() for value in args.input]
    missing = [str(path) for path in input_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"input HDF5 files do not exist: {missing}")

    report = build_dataset(
        input_paths=input_paths,
        output_path=Path(args.output).expanduser().resolve(),
        add_online_timesteps=args.add_online_timesteps,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
