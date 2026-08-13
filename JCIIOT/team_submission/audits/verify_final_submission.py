"""Verify the final five-model submission manifest and score evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MODELS = {
    "L1": ("team_submission/models/final/l1/model_epoch_20.pth", "1b13ed397d5d52141a9a32610dfc4a8829bdc6f4d5164f97ce9e5bd01f7e251e"),
    "L2": ("team_submission/models/final/l2/model_epoch_50.pth", "9352d87f4c8ebbb81b3ccd63b09a2442fed4ec45f686121e1b91bb02c3ba1bbe"),
    "L3": ("team_submission/models/final/l3/model_epoch_100.pth", "6052020c4cd75321d29dd9e108e9a0f4b34c3f7823e36831c2666a09bc074c52"),
    "L4": ("team_submission/models/final/l4/model_epoch_50.pth", "0aa08fcea60ad6a79fd59632b0fda5101cfaac37d5b2a50fb6881a203419ef8f"),
    "L5": ("team_submission/models/final/l5/model_epoch_100.pth", "f9c6f32cc7ff7d66bae08adb1bf0dfc0f6f36010db68e76723a6a10468bbea1f"),
}

SCORES = {"L1": 10, "L2": 15, "L3": 20, "L4": 25, "L5": 30}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    failures: list[str] = []
    params = json.loads((ROOT / "knowledge/robot_params.json").read_text())
    routed = params["grasp_policy"]["task_checkpoints"]

    for level, (relative, expected_hash) in MODELS.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"{level}: missing model {relative}")
        elif sha256(path) != expected_hash:
            failures.append(f"{level}: model SHA-256 mismatch")

        evidence = ROOT / "team_submission/evidence" / level
        for name in ("score.json", "result.json", "trajectory.json"):
            if not (evidence / name).is_file():
                failures.append(f"{level}: missing evidence {name}")
        if (evidence / "score.json").is_file():
            score = json.loads((evidence / "score.json").read_text())
            if score.get("status") != "OK" or score.get("score") != SCORES[level]:
                failures.append(f"{level}: score evidence is not full-score OK")

    expected_routes = {
        "FactorySorting1_3FO3ERFHISEM": MODELS["L1"][0],
        "FactorySorting3_3FO3ERRPH7X9": MODELS["L2"][0],
        "FactorySorting5_3FO3ERTPXEUT": MODELS["L3"][0],
        "FactorySorting7_3FO3ERFKY9RN": MODELS["L4"][0],
        "FactorySorting9_3FO3ERT2C5FP": MODELS["L5"][0],
    }
    if routed != expected_routes:
        failures.append("robot_params task_checkpoints do not match manifest")

    boundary = json.loads(
        (ROOT / "team_submission/audits/official_boundary_audit.json").read_text()
    )
    if not boundary.get("summary", {}).get("compliant"):
        failures.append("official protected-boundary audit is not compliant")

    if failures:
        print("Final submission verification: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Final submission verification: PASSED")
    print("Models: 5/5 | Full-score evidence: 5/5 | Total: 100/100")
    print("Protected-boundary audit: compliant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
