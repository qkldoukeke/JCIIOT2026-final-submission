"""Build a portable, evidence-only JCIIOT submission ZIP."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent
MANIFEST_PATH = ROOT / "team_submission" / "submission_manifest.json"
SOURCE_INDEX_PATH = ROOT / "team_submission" / "evidence" / "EVIDENCE_INDEX.json"
OUTPUT_PATH = REPOSITORY_ROOT / "JCIIOT2026.zip"
FIXED_TIMESTAMP = (2026, 8, 14, 0, 0, 0)
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"(?:^|[\"'\s])/Users/", re.MULTILINE),
    re.compile(r"(?:^|[\"'\s])/home/", re.MULTILINE),
    re.compile(r"(?:^|[\"'\s])[A-Za-z]:[\\/]", re.MULTILINE),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def portable_string(value: str) -> str:
    normalized = value.replace("\\", "/")
    marker = "/JCIIOT/"
    if marker in normalized and (
        normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized)
    ):
        return normalized.split(marker, 1)[1]
    return value


def make_portable(value):
    if isinstance(value, dict):
        return {key: make_portable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_portable(item) for item in value]
    if isinstance(value, str):
        return portable_string(value)
    return value


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def assert_portable(name: str, data: bytes) -> None:
    text = data.decode("utf-8")
    for pattern in ABSOLUTE_PATH_PATTERNS:
        if pattern.search(text):
            raise RuntimeError(f"local absolute path found in {name}: {pattern.pattern}")


def write_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    assert_portable(name, data)
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_summary(manifest: dict) -> bytes:
    identity = manifest["identity"]
    result = manifest["result_summary"]
    text = f"""# JCIIOT 2026 Submission Evidence Package

- Team: {identity['team_name']}
- Participant ID: {identity['participant_id']}
- Score: {result['score']}/{result['max_score']}
- Total elapsed time: {result['total_elapsed_sec']} s
- Repository: {identity['repository_url']}
- Leaderboard Issue: {identity['leaderboard_issue_url']}

This ZIP is a portable evidence-and-documentation package, not a complete source-code
or model archive. Reproduce the project from the repository and run `git lfs pull`
before verification. The 15 evidence JSON files below are portable copies: only local
machine path prefixes were converted to repository-relative paths. Source-file hashes
are retained in `evidence_index.json`; packaged-copy hashes are recorded separately.
"""
    return text.encode("utf-8")


def build_package(output_path: Path = OUTPUT_PATH) -> None:
    manifest = read_json(MANIFEST_PATH)
    source_index = read_json(SOURCE_INDEX_PATH)
    if manifest.get("level_results") != source_index.get("levels"):
        raise RuntimeError("submission manifest and evidence index differ")
    package_index = {
        "schema_version": 1,
        "portable_copy": True,
        "source_evidence_immutable": True,
        "path_normalization": (
            "Only absolute prefixes ending in /JCIIOT/ were removed from packaged "
            "JSON copies; repository source evidence was not modified."
        ),
        "levels": {},
    }

    document_map = {
        "technical_report.md": REPOSITORY_ROOT / "技术报告.md",
        "novelty_statement.md": REPOSITORY_ROOT / "新颖性声明.md",
        "reproduction_guide.md": REPOSITORY_ROOT / "复现指南.md",
        "compliance_statement.md": REPOSITORY_ROOT / "提交合规说明.md",
    }

    with zipfile.ZipFile(output_path, "w") as archive:
        write_entry(archive, "submission_summary.md", build_summary(manifest))
        for archive_name, source_path in document_map.items():
            write_entry(archive, archive_name, source_path.read_bytes())
        write_entry(
            archive,
            "submission_manifest.json",
            json_bytes(make_portable(manifest)),
        )

        for level, level_record in source_index["levels"].items():
            packaged_level = {
                "score": level_record["score"],
                "elapsed_sec": level_record["elapsed_sec"],
                "environment": level_record["environment"],
                "checkpoint": level_record["checkpoint"],
                "files": {},
            }
            for kind, evidence_record in level_record["evidence"].items():
                source_path = ROOT / evidence_record["path"]
                if sha256_file(source_path) != evidence_record["sha256"]:
                    raise RuntimeError(f"source evidence hash mismatch: {source_path}")
                portable = json_bytes(make_portable(read_json(source_path)))
                archive_name = f"evidence/{level}/{kind}.json"
                write_entry(archive, archive_name, portable)
                packaged_level["files"][kind] = {
                    "archive_path": archive_name,
                    "source_path": evidence_record["path"],
                    "source_sha256": evidence_record["sha256"],
                    "package_sha256": sha256_bytes(portable),
                }
            package_index["levels"][level] = packaged_level

        write_entry(archive, "evidence_index.json", json_bytes(package_index))
        index_lines = [
            "# Evidence Package Index",
            "",
            "The repository evidence is immutable. ZIP copies differ only because local path prefixes were removed.",
            "",
            "| Level | Score | Time (s) | score.json | result.json | trajectory.json |",
            "|---|---:|---:|---|---|---|",
        ]
        for level, record in package_index["levels"].items():
            cells = [record["files"][kind]["package_sha256"][:12] for kind in ("score", "result", "trajectory")]
            index_lines.append(
                f"| {level} | {record['score']} | {record['elapsed_sec']} | "
                f"`{cells[0]}…` | `{cells[1]}…` | `{cells[2]}…` |"
            )
        write_entry(archive, "evidence_index.md", ("\n".join(index_lines) + "\n").encode("utf-8"))

    print(f"Built {output_path}")
    print(f"SHA-256: {sha256_file(output_path)}")


if __name__ == "__main__":
    build_package()
