"""Prove that the full-score runtime path and original evidence are unchanged."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
BASELINE_COMMIT = "4b9d7ed71d57e307d7a0bb3b41f55201704a466e"
INDEX_PATH = ROOT / "team_submission" / "evidence" / "EVIDENCE_INDEX.json"
REPORT_JSON = ROOT / "team_submission" / "audits" / "runtime_immutability_report.json"
REPORT_MD = ROOT / "team_submission" / "audits" / "runtime_immutability_report.md"

RUNTIME_PATHS = (
    "JCIIOT/src/robot_agent/skills",
    "JCIIOT/knowledge/robot_params.json",
    "JCIIOT/src/robot_agent/workflows",
    "JCIIOT/app.py",
    "JCIIOT/knowledge/task_config.json",
    "JCIIOT/src/robot_agent/core",
    "JCIIOT/src/robot_agent/environments",
)

ALLOWED_EXACT = {
    "JCIIOT/robosuite/dataset/table_setup_from_dishwasher_sample.hdf5",
    "JCIIOT/robosuite/robosuite/models/assets/objects/siemens/mujoco_original/meshes/parts/lowered_table_meshes_70cm_v2.zip",
    "JCIIOT/robosuite/robosuite/models/assets/objects/siemens/mujoco_original/meshes/parts/lowered_table_meshes_70cm_v3_fix_front_pillars.zip",
    "JCIIOT/robosuite/robosuite/models/assets/objects/siemens/mujoco_original/meshes/parts/lowered_table_meshes_70cm_v4_shorten_front_legs.zip",
    "JCIIOT/robosuite/robosuite/models/assets/objects/siemens/mujoco_original/meshes/parts/lowered_table_meshes_70cm_v5_piecewise_front_supports.zip",
    "JCIIOT/team_submission/TRAINING_DATA_MANIFEST.md",
    "JCIIOT/team_submission/submission_manifest.json",
    "JCIIOT2026.zip",
    "README.md",
    "复现指南.md",
    "实验开发日志.md",
    "技术报告.md",
    "排行榜提交草稿.md",
    "提交合规说明.md",
    "最终提交清单.md",
}
ALLOWED_PREFIXES = (
    "JCIIOT/team_submission/audits/",
    "JCIIOT/team_submission/evidence/EVIDENCE_INDEX.",
    "JCIIOT/team_submission/tools/",
    "JCIIOT/team_submission/training_configs/",
    "docs/superpowers/",
)


def run_git(*args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    if result.returncode:
        stderr = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(stderr.strip())
    return result.stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def changed_paths() -> list[str]:
    raw = run_git("status", "--porcelain=v1", "-z", text=False)
    paths = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        paths.append(record[3:].decode("utf-8", errors="replace"))
    return sorted(set(paths))


def is_allowed(path: str) -> bool:
    return path in ALLOWED_EXACT or any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def main() -> int:
    runtime_diff = run_git("diff", "--name-only", BASELINE_COMMIT, "--", *RUNTIME_PATHS)
    runtime_changes = [line for line in runtime_diff.splitlines() if line]
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    evidence = []
    for level, level_record in index["levels"].items():
        for kind, file_record in level_record["evidence"].items():
            relative = file_record["path"]
            expected = file_record["sha256"]
            current = sha256_file(ROOT / relative)
            blob = run_git("show", f"{BASELINE_COMMIT}:JCIIOT/{relative}", text=False)
            baseline = sha256_bytes(blob)
            evidence.append(
                {
                    "level": level,
                    "kind": kind,
                    "path": relative,
                    "expected_sha256": expected,
                    "current_sha256": current,
                    "baseline_sha256": baseline,
                    "unchanged": current == baseline == expected,
                }
            )

    changes = changed_paths()
    disallowed = [path for path in changes if not is_allowed(path)]
    passed = not runtime_changes and not disallowed and all(item["unchanged"] for item in evidence)
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_baseline_commit": BASELINE_COMMIT,
        "runtime_paths": list(RUNTIME_PATHS),
        "runtime_changed_files": runtime_changes,
        "working_tree_changed_files": changes,
        "disallowed_changed_files": disallowed,
        "evidence": evidence,
        "passed": passed,
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Runtime Immutability Report",
        "",
        f"- Baseline commit: `{BASELINE_COMMIT}`",
        f"- Runtime changed files: **{len(runtime_changes)}**",
        f"- Disallowed changed files: **{len(disallowed)}**",
        f"- Original evidence files unchanged: **{sum(item['unchanged'] for item in evidence)}/15**",
        f"- Result: **{'PASS' if passed else 'FAIL'}**",
        "",
        "The protected runtime path covers skills, parameters, workflows, app.py, task configuration, core, and environments.",
        "The five restored official resources and submission-only documents/audits are explicitly allowlisted.",
    ]
    if runtime_changes:
        lines.extend(["", "## Runtime changes", "", *[f"- `{path}`" for path in runtime_changes]])
    if disallowed:
        lines.extend(["", "## Disallowed changes", "", *[f"- `{path}`" for path in disallowed]])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Runtime immutability: {'PASSED' if passed else 'FAILED'}")
    print(f"Runtime changes: {len(runtime_changes)}")
    print(f"Evidence unchanged: {sum(item['unchanged'] for item in evidence)}/15")
    print(f"Disallowed changes: {len(disallowed)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
