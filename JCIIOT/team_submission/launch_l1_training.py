from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(os.environ.get("JCI_PYTHON") or sys.executable).resolve()
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT
    / "team_submission"
    / "training_configs"
    / "factory_sorting_l1_nomarker_team_bc_50.json"
)
LOG_ROOT = PROJECT_ROOT / "team_submission" / "training_runs"
ACTIVE_RUN_PATH = LOG_ROOT / "l1_training_active.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the latest run for the same robomimic experiment name.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="L1 robomimic config to launch.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    if not PYTHON_EXE.is_file():
        raise FileNotFoundError(PYTHON_EXE)
    if not config_path.is_file():
        raise FileNotFoundError(config_path)

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_kind = "resume" if args.resume else "fresh"
    log_prefix = config_path.stem
    stdout_path = LOG_ROOT / f"{log_prefix}_{run_kind}_{stamp}.stdout.log"
    stderr_path = LOG_ROOT / f"{log_prefix}_{run_kind}_{stamp}.stderr.log"

    command = [
        str(PYTHON_EXE),
        "-u",
        "-m",
        "robomimic.scripts.train",
        "--config",
        str(config_path),
    ]
    if args.resume:
        command.append("--resume")

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=stdout_file,
            stderr=stderr_file,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    run_info = {
        "pid": process.pid,
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config": str(config_path),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "random_initialization": True,
        "resume": bool(args.resume),
        "resume_checkpoint": "latest team checkpoint" if args.resume else None,
    }
    ACTIVE_RUN_PATH.write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(run_info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
