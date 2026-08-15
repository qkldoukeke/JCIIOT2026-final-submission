"""Validate all five team-generated SOP artifacts and their provenance."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path, project_root: Path) -> str:
    """Store repository-relative paths so audit output is cross-platform."""
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    task_config = project_root / "knowledge" / "task_config.json"
    generated_root = project_root / "team_submission" / "generated_sops"
    active_path = project_root / "team_submission" / "knowledge" / "current_generated_sop.md"
    map_root = (
        project_root
        / "robosuite"
        / "robosuite"
        / "environments"
        / "factory_sorting"
        / "generated_maps"
    )
    catalog = json.loads(task_config.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = []

    for index, task in enumerate(catalog["tasks"]):
        level = str(task["level"])
        case_number = index * 2 + 1
        docx = project_root / "sop+prompt" / f"JCIIOT 2026 case {case_number} SOP.docx"
        generated = generated_root / f"generated_sop_{level.lower()}.md"
        semantic_map = map_root / f"{task['scene_prefix']}_scene_regenerated_semantic_map.json"
        checks: dict[str, bool] = {
            "docx_exists": docx.exists(),
            "generated_sop_exists": generated.exists(),
            "semantic_map_exists": semantic_map.exists(),
        }
        content = generated.read_text(encoding="utf-8") if generated.exists() else ""
        required_markers = {
            "level": f"CURRENT LEVEL: `{level}`",
            "source_docx": f"Source DOCX: `{docx.name}`",
            "environment": f"Environment: `{task['env_name']}`",
            "source": f"Source station ID: `{task['source']}`",
            "target": f"Target station ID: `{task['target']}`",
            "scene_map": f"Scene map: `{semantic_map.name}`",
        }
        for name, marker in required_markers.items():
            checks[f"marker_{name}"] = marker in content
        for object_name in task.get("object", []):
            checks[f"object_{object_name}"] = f"`{object_name}`" in content

        compliant = all(checks.values())
        records.append(
            {
                "level": level,
                "case_number": case_number,
                "environment": task["env_name"],
                "source": task["source"],
                "target": task["target"],
                "objects": task.get("object", []),
                "docx": portable_path(docx, project_root),
                "docx_sha256": sha256(docx) if docx.exists() else None,
                "semantic_map": portable_path(semantic_map, project_root),
                "semantic_map_sha256": sha256(semantic_map) if semantic_map.exists() else None,
                "generated_sop": portable_path(generated, project_root),
                "generated_sop_sha256": sha256(generated) if generated.exists() else None,
                "checks": checks,
                "compliant": compliant,
            }
        )

    active_content = active_path.read_text(encoding="utf-8") if active_path.exists() else ""
    active_level = next(
        (
            record["level"]
            for record in records
            if f"CURRENT LEVEL: `{record['level']}`" in active_content
        ),
        None,
    )
    active_matches_archive = False
    if active_level:
        archive = generated_root / f"generated_sop_{str(active_level).lower()}.md"
        active_matches_archive = archive.exists() and active_path.read_bytes() == archive.read_bytes()

    library_path = project_root / "src" / "robot_agent" / "skills" / "library.py"
    library_text = library_path.read_text(encoding="utf-8")
    automatic_activation = (
        "def _activate_generated_sop_for_scene" in library_text
        and "_activate_generated_sop_for_scene(scene_context)" in library_text
        and "configured_task(scene_context)" in library_text
    )
    compliant = (
        all(record["compliant"] for record in records)
        and bool(active_level)
        and active_matches_archive
        and automatic_activation
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_config": portable_path(task_config, project_root),
        "task_config_sha256": sha256(task_config),
        "summary": {
            "sop_count": len(records),
            "valid_sops": sum(bool(record["compliant"]) for record in records),
            "active_level": active_level,
            "active_matches_archive": active_matches_archive,
            "automatic_environment_activation": automatic_activation,
            "compliant": compliant,
        },
        "records": records,
    }

    output_json = Path(__file__).with_name("generated_sop_audit.json")
    output_md = output_json.with_suffix(".md")
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 团队生成 SOP 审计",
        "",
        f"- 结论：**{'通过' if compliant else '不通过'}**",
        f"- 已生成并验证：`{report['summary']['valid_sops']}/{len(records)}`",
        f"- 当前激活：`{active_level}`",
        f"- 当前文件与归档一致：`{active_matches_archive}`",
        f"- Execute 按环境自动激活：`{automatic_activation}`",
        "",
        "| 关卡 | Word | 环境 | 来源 | 目标 | 结果 |",
        "|---|---|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            f"| {record['level']} | case {record['case_number']} | "
            f"`{record['environment']}` | `{record['source']}` | "
            f"`{record['target']}` | {'通过' if record['compliant'] else '失败'} |"
        )
    lines.extend(
        [
            "",
            "每份记录均保存 Word、语义地图和生成 Markdown 的 SHA-256。",
            "坐标来源是匹配场景的语义地图；Word 只提供任务语义，不从图片猜测世界坐标。",
            "",
        ]
    )
    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(output_md.read_text(encoding="utf-8"), end="")
    print(f"JSON: {output_json}")
    return 0 if compliant else 1


if __name__ == "__main__":
    raise SystemExit(main())
