"""Cross-platform verification for the final JCIIOT submission."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
MANIFEST_PATH = ROOT / "team_submission" / "submission_manifest.json"
EVIDENCE_INDEX_PATH = ROOT / "team_submission" / "evidence" / "EVIDENCE_INDEX.json"
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RUNTIME_PATHS = (
    "JCIIOT/src/robot_agent/skills",
    "JCIIOT/knowledge/robot_params.json",
    "JCIIOT/src/robot_agent/workflows",
    "JCIIOT/app.py",
    "JCIIOT/knowledge/task_config.json",
    "JCIIOT/src/robot_agent/core",
    "JCIIOT/src/robot_agent/environments",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size > 4096:
        return False
    return path.read_bytes().startswith(LFS_HEADER)


def display_path(path: Path) -> str:
    """Return a portable project-relative label when possible."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def check_file_hash(path: Path, expected: str) -> str | None:
    if not path.is_file():
        return f"missing file: {display_path(path)}"
    if is_lfs_pointer(path):
        return (
            f"model remains a Git LFS pointer: {display_path(path)}\n"
            "  git lfs install\n  git lfs pull"
        )
    actual = sha256_file(path)
    if actual != expected:
        return f"SHA-256 mismatch: {display_path(path)} ({actual})"
    return None


def check_python_json(manifest: dict) -> list[str]:
    failures: list[str] = []
    paths = list((ROOT / "team_submission").rglob("*.json"))
    paths += [ROOT / "knowledge" / "robot_params.json"]
    for path in sorted(set(paths)):
        try:
            read_json(path)
        except Exception as exc:
            failures.append(f"invalid UTF-8 JSON {path.relative_to(ROOT)}: {exc}")
    for path in sorted((ROOT / "team_submission").rglob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            failures.append(f"invalid UTF-8 Python {path.relative_to(ROOT)}: {exc}")
    release_commit = manifest.get("version_control", {}).get("release_content_commit")
    if not isinstance(release_commit, str) or not COMMIT_SHA_PATTERN.fullmatch(release_commit):
        failures.append("manifest release_content_commit is not finalized")
    return failures


def check_models(manifest: dict) -> list[str]:
    failures: list[str] = []
    for name, record in manifest["models"].items():
        path = ROOT / record["path"]
        failure = check_file_hash(path, record["sha256"])
        if failure:
            failures.append(f"{name}: {failure}")
        elif path.stat().st_size != record["size"]:
            failures.append(f"{name}: size mismatch for {record['path']}")
    return failures


def _git_blob(commit: str, relative_to_root: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:JCIIOT/{relative_to_root}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def check_evidence(manifest: dict) -> list[str]:
    failures: list[str] = []
    index = read_json(EVIDENCE_INDEX_PATH)
    baseline = manifest["version_control"]["runtime_baseline_commit"]
    total_score = 0
    total_elapsed = 0.0
    for level, record in index["levels"].items():
        total_score += int(record["score"])
        total_elapsed += float(record["elapsed_sec"])
        for kind, evidence in record["evidence"].items():
            relative = evidence["path"]
            path = ROOT / relative
            if not path.is_file():
                failures.append(f"{level} {kind}: missing {relative}")
                continue
            actual = sha256_file(path)
            if actual != evidence["sha256"]:
                failures.append(f"{level} {kind}: indexed SHA-256 mismatch")
            try:
                baseline_sha = sha256_bytes(_git_blob(baseline, relative))
            except RuntimeError as exc:
                failures.append(f"{level} {kind}: cannot read baseline blob: {exc}")
            else:
                if baseline_sha != evidence["sha256"]:
                    failures.append(f"{level} {kind}: changed since runtime baseline")
        score_payload = read_json(ROOT / record["evidence"]["score"]["path"])
        if score_payload.get("status") != "OK":
            failures.append(f"{level}: score status is not OK")
        if score_payload.get("score") != record["score"]:
            failures.append(f"{level}: score differs from evidence index")
        if float(score_payload.get("elapsed_sec", -1)) != float(record["elapsed_sec"]):
            failures.append(f"{level}: elapsed time differs from evidence index")
        if score_payload.get("env_name") != record["environment"]:
            failures.append(f"{level}: environment differs from evidence index")
    summary = manifest["result_summary"]
    if total_score != summary["score"] or summary["score"] != summary["max_score"]:
        failures.append("manifest total score does not equal indexed full score")
    if abs(total_elapsed - float(summary["total_elapsed_sec"])) > 1e-6:
        failures.append("manifest total elapsed time does not equal evidence index")
    return failures


def check_routing(manifest: dict) -> list[str]:
    failures: list[str] = []
    params = read_json(ROOT / "knowledge" / "robot_params.json")
    policy = params.get("grasp_policy", {})
    if policy.get("task_checkpoints") != manifest["task_routing"]:
        failures.append("robot_params task_checkpoints differ from manifest")
    enabled = bool(policy.get("scripted_first_with_bc_recovery"))
    actual_router = "scripted_first_with_bc_recovery" if enabled else "bc_first"
    if actual_router != manifest["grasp_router"]:
        failures.append("grasp router differs from manifest")
    return failures


def check_generated_sops(_: dict) -> list[str]:
    failures: list[str] = []
    audit_path = ROOT / "team_submission" / "audits" / "generated_sop_audit.json"
    audit = read_json(audit_path)
    if not audit.get("summary", {}).get("compliant"):
        failures.append("generated SOP audit is not compliant")
    if audit.get("summary", {}).get("valid_sops") != 5:
        failures.append("generated SOP audit does not report 5 valid SOPs")
    for record in audit.get("records", []):
        path = ROOT / "team_submission" / "generated_sops" / f"generated_sop_{record['level'].lower()}.md"
        if not path.is_file() or sha256_file(path) != record.get("generated_sop_sha256"):
            failures.append(f"{record.get('level')}: generated SOP hash mismatch")
    return failures


def check_boundary(manifest: dict) -> list[str]:
    failures: list[str] = []
    audit = read_json(ROOT / "team_submission" / "audits" / "official_boundary_audit.json")
    official = manifest["official_reference"]
    for key in ("reference_repository", "reference_commit", "reference_archive_url"):
        manifest_key = {
            "reference_repository": "repository_url",
            "reference_commit": "commit",
            "reference_archive_url": "archive_url",
        }[key]
        if audit.get(key) != official[manifest_key]:
            failures.append(f"protected audit {key} differs from manifest")
    if audit.get("reference_zip_sha256") != official["archive_sha256"]:
        failures.append("protected audit archive SHA-256 differs from manifest")
    summary = audit.get("summary", {})
    if not summary.get("compliant") or summary.get("violations") != 0:
        failures.append("protected-boundary audit is not compliant")
    expected = official["protected_summary"]
    statuses = summary.get("status_counts", {})
    observed = {
        "reference_files": summary.get("reference_files"),
        "ordinary_identical": statuses.get("identical", 0),
        "lfs_pointer_intact": statuses.get("lfs_pointer_intact", 0),
        "lfs_materialized": statuses.get("lfs_materialized", 0),
        "lfs_unavailable": statuses.get("lfs_object_unavailable", 0),
        "modified": statuses.get("modified", 0),
        "missing": statuses.get("missing", 0),
        "violations": summary.get("violations"),
    }
    if observed != expected:
        failures.append("protected-boundary summary differs from manifest")
    baseline = manifest["version_control"]["runtime_baseline_commit"]
    runtime_diff = subprocess.run(
        ["git", "diff", "--name-only", baseline, "--", *RUNTIME_PATHS],
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if runtime_diff.returncode:
        failures.append(f"cannot compare runtime path: {runtime_diff.stderr.strip()}")
    elif runtime_diff.stdout.strip():
        failures.append(
            "runtime path changed since full-score baseline: "
            + ", ".join(runtime_diff.stdout.splitlines())
        )
    return failures


def check_documents(manifest: dict) -> list[str]:
    failures: list[str] = []
    identity = manifest["identity"]
    official = manifest["official_reference"]
    levels = read_json(EVIDENCE_INDEX_PATH)["levels"]
    expected_by_document = {
        "README.md": [
            identity["team_name"], identity["participant_id"],
            identity["repository_url"], identity["leaderboard_issue_url"],
            official["commit"], official["archive_sha256"], "100/100",
        ] + [f"{item['elapsed_sec']:.3f}" for item in levels.values()],
        "技术报告.md": [official["commit"], official["archive_sha256"], "100"],
        "复现指南.md": [identity["repository_url"], official["commit"], official["archive_sha256"]],
        "提交合规说明.md": [official["commit"], official["archive_sha256"], "100/100"],
        "最终提交清单.md": [identity["team_name"], identity["participant_id"], identity["leaderboard_issue_url"]],
        "排行榜提交草稿.md": [identity["team_name"], identity["participant_id"], identity["leaderboard_issue_url"], official["commit"]],
        "实验开发日志.md": [official["commit"], official["archive_sha256"], "267.760"],
    }
    forbidden = ("<请填写>", "01032e8dc97fcd376502b71327ad8cbea6b6589b")
    for name, tokens in expected_by_document.items():
        path = REPOSITORY_ROOT / name
        if not path.is_file():
            failures.append(f"missing document: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if str(token) not in text:
                failures.append(f"{name}: missing manifest fact {token}")
        for token in forbidden:
            if token in text:
                failures.append(f"{name}: contains stale token {token}")
    return failures


def main() -> int:
    manifest = read_json(MANIFEST_PATH)
    groups: list[tuple[str, Callable[[dict], list[str]]]] = [
        ("Python / JSON", check_python_json),
        ("Model files", check_models),
        ("Evidence integrity", check_evidence),
        ("Task checkpoint routing", check_routing),
        ("Generated SOP", check_generated_sops),
        ("Protected boundary", check_boundary),
        ("Documentation consistency", check_documents),
    ]
    failed = False
    for label, checker in groups:
        failures = checker(manifest)
        print(f"[{'FAIL' if failures else 'PASS'}] {label}")
        for failure in failures:
            print(f"  - {failure}")
        failed = failed or bool(failures)
    if failed:
        print("Final submission verification: FAILED")
        return 1
    print("Final submission verification: PASSED")
    print("Models: 6/6 | Evidence: 15/15 | Total: 100/100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
