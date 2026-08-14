"""Validate that all archived robomimic configs are portable from JCIIOT/."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from pathlib import PureWindowsPath


ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = ROOT / "team_submission" / "training_configs"
DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _resolve_project_path(value: str) -> Path:
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise ValueError(f"absolute path is not portable: {value}")
    if DRIVE_PATH.match(value) or value.startswith("/Users/"):
        raise ValueError(f"machine-specific path is not portable: {value}")
    resolved = (ROOT / value).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes project root: {value}") from exc
    return resolved


def validate_config(path: Path, *, require_data: bool) -> list[str]:
    failures: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid UTF-8 JSON: {exc}"]

    for index, item in enumerate(payload.get("train", {}).get("data", [])):
        value = str(item.get("path", ""))
        try:
            resolved = _resolve_project_path(value)
        except ValueError as exc:
            failures.append(f"train.data[{index}].path: {exc}")
            continue
        if require_data and not resolved.is_file():
            failures.append(f"training data not found: {value}")

    output_dir = str(payload.get("train", {}).get("output_dir", ""))
    try:
        _resolve_project_path(output_dir)
    except ValueError as exc:
        failures.append(f"train.output_dir: {exc}")

    checkpoint = payload.get("experiment", {}).get("ckpt_path")
    if checkpoint:
        try:
            _resolve_project_path(str(checkpoint))
        except ValueError as exc:
            failures.append(f"experiment.ckpt_path: {exc}")

    try:
        project_root = str(ROOT)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from robomimic.config import config_factory

        config = config_factory(payload["algo_name"])
        config.update(payload)
    except Exception as exc:
        failures.append(f"robomimic config load failed: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-data",
        action="store_true",
        help="also require every ignored local HDF5 file to exist",
    )
    args = parser.parse_args()

    configs = sorted(CONFIG_ROOT.glob("*.json"))
    failures: list[str] = []
    for path in configs:
        for failure in validate_config(path, require_data=args.require_data):
            failures.append(f"{path.name}: {failure}")

    if failures:
        print(f"Training config validation: FAILED ({len(failures)} errors)")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Training config validation: PASSED ({len(configs)} configs)")
    print(f"Resolution root: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
