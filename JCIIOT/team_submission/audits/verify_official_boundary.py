"""Verify organizer-maintained files against the untouched GitHub ZIP.

The reference archive is opened read-only.  The report treats a Git LFS
pointer as compliant when the current materialized file matches the pointer's
declared SHA-256 and size.  Runtime caches, packaging metadata and collected
demonstrations are reported separately and must be excluded from submission.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile


PROTECTED_EXACT = {
    "app.py",
    "knowledge/task_config.json",
}

PROTECTED_PREFIXES = (
    "robosuite/",
    "src/robot_agent/core/",
    "src/robot_agent/environments/",
)


def is_protected(relative_path: str) -> bool:
    path = relative_path.replace("\\", "/")
    return path.startswith(PROTECTED_PREFIXES) or path in PROTECTED_EXACT


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_entry(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(entry, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_lfs_pointer(data: bytes) -> dict[str, object] | None:
    if not data.startswith(b"version https://git-lfs.github.com/spec/v1"):
        return None
    text = data.decode("utf-8", errors="strict")
    oid = re.search(r"^oid sha256:([0-9a-f]{64})$", text, re.MULTILINE)
    size = re.search(r"^size (\d+)$", text, re.MULTILINE)
    if not oid or not size:
        return None
    return {"sha256": oid.group(1), "size": int(size.group(1))}


def classify_extra(relative_path: str) -> str:
    path = relative_path.replace("\\", "/")
    if "__pycache__/" in path or path.endswith(".pyc"):
        return "runtime_cache"
    if "/demonstrations_private/" in path:
        return "collected_demonstration"
    if path.startswith("robosuite/robosuite.egg-info/"):
        return "packaging_metadata"
    return "unexpected_protected_extra"


def reference_prefix(archive: zipfile.ZipFile) -> str:
    candidates = {
        name[: -len("JCIIOT/app.py")]
        for name in archive.namelist()
        if name.endswith("JCIIOT/app.py")
    }
    if len(candidates) != 1:
        raise RuntimeError(f"Cannot resolve unique JCIIOT root: {sorted(candidates)}")
    return candidates.pop() + "JCIIOT/"


def audit(reference_zip: Path, current_root: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    extras: list[dict[str, object]] = []

    with zipfile.ZipFile(reference_zip, "r") as archive:
        prefix = reference_prefix(archive)
        reference_entries = {
            info.filename[len(prefix) :]: info
            for info in archive.infolist()
            if info.filename.startswith(prefix)
            and not info.is_dir()
            and is_protected(info.filename[len(prefix) :])
        }
        current_files = {
            path.relative_to(current_root).as_posix(): path
            for path in current_root.rglob("*")
            if path.is_file()
            and is_protected(path.relative_to(current_root).as_posix())
        }

        for relative_path in sorted(reference_entries):
            entry = reference_entries[relative_path]
            current_path = current_files.get(relative_path)
            reference_data = archive.read(entry)
            reference_sha = hashlib.sha256(reference_data).hexdigest()
            record: dict[str, object] = {
                "path": relative_path,
                "reference_size": entry.file_size,
                "reference_sha256": reference_sha,
            }
            if current_path is None:
                record.update(status="missing", compliant=False)
                records.append(record)
                continue

            current_size = current_path.stat().st_size
            current_sha = sha256_file(current_path)
            record.update(
                current_size=current_size,
                current_sha256=current_sha,
            )
            if current_size == entry.file_size and current_sha == reference_sha:
                record.update(status="identical", compliant=True)
            else:
                pointer = parse_lfs_pointer(reference_data)
                if (
                    pointer
                    and current_size == pointer["size"]
                    and current_sha == pointer["sha256"]
                ):
                    record.update(
                        status="lfs_materialized",
                        compliant=True,
                        lfs_oid_sha256=pointer["sha256"],
                        lfs_size=pointer["size"],
                    )
                else:
                    record.update(status="modified", compliant=False)
            records.append(record)

        for relative_path in sorted(set(current_files) - set(reference_entries)):
            path = current_files[relative_path]
            classification = classify_extra(relative_path)
            extras.append(
                {
                    "path": relative_path,
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "classification": classification,
                    "compliant": classification != "unexpected_protected_extra",
                    "submission_action": "exclude",
                }
            )

    status_counts: dict[str, int] = {}
    for record in records:
        key = str(record["status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    extra_counts: dict[str, int] = {}
    for record in extras:
        key = str(record["classification"])
        extra_counts[key] = extra_counts.get(key, 0) + 1

    violations = [record for record in records + extras if not record["compliant"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_zip": str(reference_zip.resolve()),
        "reference_zip_sha256": sha256_file(reference_zip),
        "current_root": str(current_root.resolve()),
        "protected_rules": {
            "prefixes": list(PROTECTED_PREFIXES),
            "exact_paths": sorted(PROTECTED_EXACT),
        },
        "summary": {
            "reference_files": len(records),
            "status_counts": status_counts,
            "protected_extras": len(extras),
            "extra_counts": extra_counts,
            "violations": len(violations),
            "compliant": not violations,
        },
        "violations": violations,
        "files": records,
        "extras": extras,
    }


def markdown_summary(report: dict[str, object]) -> str:
    summary = report["summary"]
    statuses = summary["status_counts"]
    extras = summary["extra_counts"]
    compliant = "通过" if summary["compliant"] else "不通过"
    lines = [
        "# 主办方维护边界审计",
        "",
        f"- 结论：**{compliant}**",
        f"- 参考 ZIP：`{report['reference_zip']}`",
        f"- 参考 ZIP SHA-256：`{report['reference_zip_sha256']}`",
        f"- 受保护参考文件：`{summary['reference_files']}`",
        f"- 逐字节一致：`{statuses.get('identical', 0)}`",
        f"- Git LFS 正确实体化：`{statuses.get('lfs_materialized', 0)}`",
        f"- 修改：`{statuses.get('modified', 0)}`",
        f"- 缺失：`{statuses.get('missing', 0)}`",
        f"- 违规项：`{summary['violations']}`",
        "",
        "## 受保护目录新增项",
        "",
        f"- Python 缓存：`{extras.get('runtime_cache', 0)}`",
        f"- 采集示范数据：`{extras.get('collected_demonstration', 0)}`",
        f"- 安装元数据：`{extras.get('packaging_metadata', 0)}`",
        f"- 未预期受保护新增项：`{extras.get('unexpected_protected_extra', 0)}`",
        "",
        "上述新增缓存、采集数据和安装元数据不属于参考源码，提交打包时必须排除。",
        "完整逐文件哈希与分类见同名 JSON 报告。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-zip",
        type=Path,
        default=project_root.parents[2] / "JCIIOT2026-master.zip",
    )
    parser.add_argument("--current-root", type=Path, default=project_root)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("official_boundary_audit.json"),
    )
    args = parser.parse_args()

    report = audit(args.reference_zip, args.current_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(markdown_summary(report), encoding="utf-8")
    print(markdown_summary(report), end="")
    print(f"JSON: {args.output.resolve()}")
    print(f"Markdown: {markdown_path.resolve()}")
    return 0 if report["summary"]["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
