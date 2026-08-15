"""Verify that competition skills do not cross the EnvBackend boundary."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "src" / "robot_agent" / "skills"
REPORT_JSON = ROOT / "team_submission" / "audits" / "skill_backend_boundary.json"
REPORT_MD = ROOT / "team_submission" / "audits" / "skill_backend_boundary.md"

FORBIDDEN_IMPORT_PREFIXES = ("robosuite", "mujoco", "mujoco_py")
FORBIDDEN_ATTRIBUTES = {
    "sim",
    "env",
    "unwrapped",
    "material_objects",
    "_env",
    "_held_crate_name",
    "_physics_policy",
    "_physics_checkpoint",
}


def audit_file(path: Path) -> list[dict]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(
                        {
                            "path": path.relative_to(ROOT).as_posix(),
                            "line": node.lineno,
                            "kind": "forbidden_import",
                            "detail": alias.name,
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "line": node.lineno,
                        "kind": "forbidden_import",
                        "detail": module,
                    }
                )
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            violations.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "line": node.lineno,
                    "kind": "forbidden_concrete_backend_attribute",
                    "detail": node.attr,
                }
            )
    return violations


def main() -> int:
    files = sorted(SKILLS_ROOT.glob("*.py"))
    violations = [item for path in files for item in audit_file(path)]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "src/robot_agent/skills/*.py",
        "policy": {
            "forbidden_import_prefixes": list(FORBIDDEN_IMPORT_PREFIXES),
            "forbidden_attributes": sorted(FORBIDDEN_ATTRIBUTES),
            "required_boundary": "robot_agent.workflows.semantic_backend.CompetitionEnvBackend",
        },
        "summary": {
            "files_scanned": len(files),
            "violations": len(violations),
            "compliant": not violations,
        },
        "violations": violations,
    }
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    status = "通过" if not violations else "不通过"
    lines = [
        "# Skill / EnvBackend 边界审计",
        "",
        f"- 结论：**{status}**",
        f"- 扫描范围：`{report['scope']}`",
        f"- Python 文件：`{len(files)}`",
        f"- 违规项：`{len(violations)}`",
        "- 规则：skill 不得直接导入 MuJoCo/robosuite，也不得访问具体环境、sim 或 backend 私有物理状态。",
        "- 物理能力边界：`robot_agent.workflows.semantic_backend.CompetitionEnvBackend`。",
        "",
    ]
    if violations:
        lines += ["## 违规明细", ""]
        for item in violations:
            lines.append(
                f"- `{item['path']}:{item['line']}` {item['kind']}: `{item['detail']}`"
            )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
