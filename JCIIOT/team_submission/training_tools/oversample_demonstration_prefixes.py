"""Create a training copy that oversamples the beginning of each demonstration.

The complete demonstrations remain present. Extra demonstrations contain only
the verified prefix window, increasing the probability that robomimic samples
the small startup actions that would otherwise be rare in a 348-step rollout.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

import h5py


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-length", type=int, default=30)
    parser.add_argument("--prefix-repeats", type=int, default=10)
    parser.add_argument(
        "--tail-start",
        type=int,
        default=-1,
        help="Optional first index of a suffix window to oversample.",
    )
    parser.add_argument("--tail-repeats", type=int, default=0)
    return parser.parse_args()


def copy_attrs(source, destination) -> None:
    for key, value in source.attrs.items():
        destination.attrs[key] = value


def ordered_demo_names(data: h5py.Group) -> list[str]:
    names = [name for name in data.keys() if name.startswith("demo_")]
    return sorted(names, key=lambda name: int(name.rsplit("_", 1)[-1]))


def create_sliced_dataset(
    source: h5py.Dataset,
    destination_parent: h5py.Group,
    name: str,
    start: int,
    end: int,
) -> None:
    values = source[start:end]
    kwargs = {}
    if source.compression is not None and values.ndim > 0:
        kwargs["compression"] = source.compression
        kwargs["compression_opts"] = source.compression_opts
        kwargs["shuffle"] = source.shuffle
    destination = destination_parent.create_dataset(name, data=values, **kwargs)
    copy_attrs(source, destination)


def copy_window_group(
    source: h5py.Group,
    destination: h5py.Group,
    start: int,
    end: int,
) -> None:
    copy_attrs(source, destination)
    for name, item in source.items():
        if isinstance(item, h5py.Dataset):
            if item.ndim == 0 or item.shape[0] < end:
                raise RuntimeError(
                    f"cannot slice {item.name} to [{start}:{end}]; shape={item.shape}"
                )
            create_sliced_dataset(item, destination, name, start, end)
        elif isinstance(item, h5py.Group):
            child = destination.create_group(name)
            copy_window_group(item, child, start, end)
        else:
            raise RuntimeError(f"unsupported HDF5 item: {item.name}")


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    if args.prefix_length <= 0 or args.prefix_repeats <= 0:
        raise ValueError("prefix length and repeats must be positive")
    if args.tail_repeats < 0:
        raise ValueError("tail repeats cannot be negative")
    if args.tail_repeats > 0 and args.tail_start < 0:
        raise ValueError("--tail-start is required when --tail-repeats is positive")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".partial")
    if temporary_path.exists():
        raise FileExistsError(temporary_path)

    try:
        with h5py.File(input_path, "r") as source, h5py.File(
            temporary_path, "w"
        ) as destination:
            if "data" not in source:
                raise RuntimeError(f"{input_path} has no /data group")
            source_data = source["data"]
            source_demos = ordered_demo_names(source_data)
            if not source_demos:
                raise RuntimeError("input contains no demonstrations")

            destination_data = destination.create_group("data")
            copy_attrs(source_data, destination_data)
            next_demo = 1
            total_samples = 0

            for source_name in source_demos:
                source_demo = source_data[source_name]
                num_samples = int(source_demo["actions"].shape[0])
                if num_samples < args.prefix_length:
                    raise RuntimeError(
                        f"{source_demo.name} has only {num_samples} samples"
                    )

                full_name = f"demo_{next_demo}"
                source.copy(source_demo, destination_data, name=full_name)
                destination_data[full_name].attrs["num_samples"] = num_samples
                destination_data[full_name].attrs["sampling_role"] = "full"
                next_demo += 1
                total_samples += num_samples

                for repeat_index in range(args.prefix_repeats):
                    prefix_name = f"demo_{next_demo}"
                    prefix_demo = destination_data.create_group(prefix_name)
                    copy_window_group(
                        source_demo,
                        prefix_demo,
                        0,
                        args.prefix_length,
                    )
                    prefix_demo.attrs["num_samples"] = args.prefix_length
                    prefix_demo.attrs["sampling_role"] = "startup_prefix"
                    prefix_demo.attrs["source_demo"] = source_name
                    prefix_demo.attrs["prefix_repeat_index"] = repeat_index
                    next_demo += 1
                    total_samples += args.prefix_length

                if args.tail_repeats > 0:
                    if args.tail_start >= num_samples:
                        raise RuntimeError(
                            f"tail start {args.tail_start} is outside {source_demo.name}"
                        )
                    tail_length = num_samples - args.tail_start
                    for repeat_index in range(args.tail_repeats):
                        tail_name = f"demo_{next_demo}"
                        tail_demo = destination_data.create_group(tail_name)
                        copy_window_group(
                            source_demo,
                            tail_demo,
                            args.tail_start,
                            num_samples,
                        )
                        tail_demo.attrs["num_samples"] = tail_length
                        tail_demo.attrs["sampling_role"] = "grasp_tail"
                        tail_demo.attrs["source_demo"] = source_name
                        tail_demo.attrs["tail_repeat_index"] = repeat_index
                        tail_demo.attrs["tail_start"] = args.tail_start
                        next_demo += 1
                        total_samples += tail_length

            output_demos = next_demo - 1
            destination_data.attrs["num_successful_demos"] = output_demos
            destination_data.attrs["training_data_oversampling"] = json.dumps(
                {
                    "created_at": datetime.datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    "source": str(input_path),
                    "source_demos": len(source_demos),
                    "prefix_length": args.prefix_length,
                    "prefix_repeats": args.prefix_repeats,
                    "tail_start": args.tail_start,
                    "tail_repeats": args.tail_repeats,
                    "output_demos": output_demos,
                    "total_samples": total_samples,
                },
                ensure_ascii=False,
            )
            destination.flush()
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    print(
        json.dumps(
            {
                "status": "PASS",
                "input": str(input_path),
                "output": str(output_path),
                "source_demos": len(source_demos),
                "prefix_length": args.prefix_length,
                "prefix_repeats": args.prefix_repeats,
                "tail_start": args.tail_start,
                "tail_repeats": args.tail_repeats,
                "output_demos": output_demos,
                "total_samples": total_samples,
                "original_file_modified": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
