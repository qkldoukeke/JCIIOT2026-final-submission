"""Run a tiny in-workspace robomimic training check from a formal config."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import torch


JCIIOT_ROOT = Path(__file__).resolve().parents[2]
if str(JCIIOT_ROOT) not in sys.path:
    sys.path.insert(0, str(JCIIOT_ROOT))

from robomimic.config import config_factory  # noqa: E402
from robomimic.scripts.train import train  # noqa: E402
from robomimic.utils import torch_utils as TorchUtils  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as config_file:
        external_config = json.load(config_file)

    config = config_factory(external_config["algo_name"])
    with config.values_unlocked():
        config.update(external_config)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        config.experiment.name = f"{config.experiment.name}_smoke_{timestamp}"
        config.experiment.logging.terminal_output_to_txt = False
        config.experiment.logging.log_tb = False
        config.experiment.save.every_n_epochs = 1
        config.experiment.epoch_every_n_steps = 3
        config.experiment.validation_epoch_every_n_steps = 3
        config.experiment.rollout.enabled = False
        config.train.output_dir = str(
            JCIIOT_ROOT / "team_submission" / "training_outputs_smoke"
        )
        config.train.hdf5_cache_mode = "low_dim"
        config.train.num_epochs = 2

    config.lock()
    device = TorchUtils.get_torch_device(try_to_use_cuda=config.train.cuda)
    if device.type != "cuda":
        raise RuntimeError(f"smoke training expected CUDA but selected {device}")

    print(f"Smoke training device: {device} ({torch.cuda.get_device_name(device)})")
    train(config=config, device=device, resume=False)
    print(
        "Smoke training CUDA peak allocated MiB: "
        f"{torch.cuda.max_memory_allocated(device) / 1024 / 1024:.1f}"
    )
    print(
        "Smoke training CUDA peak reserved MiB: "
        f"{torch.cuda.max_memory_reserved(device) / 1024 / 1024:.1f}"
    )


if __name__ == "__main__":
    main()
