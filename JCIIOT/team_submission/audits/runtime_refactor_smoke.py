"""Offline runtime smoke test for the player-owned semantic backend adapter.

This diagnostic deliberately drives registered skills without invoking an LLM.
It is not part of the competition task implementation and does not modify the
organizer backend or environment sources.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from robot_agent.core.map_loader import load_map_files
from robot_agent.core.scene_context import SceneContext
from robot_agent.core.types import ExecutionContext
from robot_agent.skills.library import wired_skills
from robot_agent.task_subprocess_runner import _choose_map_files, _configure_paths


def _run_skill(skills: dict, skill_name: str, inputs: dict) -> dict:
    skill = skills.get(skill_name)
    if skill is None:
        raise RuntimeError(f"registered skill missing: {skill_name}")
    started = time.perf_counter()
    result = skill.run(
        ExecutionContext(
            task=str(inputs.get("target") or skill_name),
            metadata={"inputs": dict(inputs)},
        )
    )
    record = {
        "skill": skill_name,
        "success": bool(result.success),
        "message": result.message,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "payload": result.payload,
    }
    print(json.dumps(record, ensure_ascii=False, default=str), flush=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument(
        "--through-place",
        action="store_true",
        help="Run source move, pick, target move, and place.",
    )
    parser.add_argument(
        "--all-objects",
        action="store_true",
        help="Repeat the full four-skill cycle for every configured object.",
    )
    args = parser.parse_args()

    tasks = json.loads(
        (PROJECT_ROOT / "knowledge" / "task_config.json").read_text(
            encoding="utf-8"
        )
    )["tasks"]
    task = tasks[args.task_index]
    configured_objects = task.get("object")
    objects = (
        [str(item) for item in configured_objects]
        if isinstance(configured_objects, list)
        else [str(configured_objects)]
    )
    if not args.all_objects:
        objects = objects[:1]

    _configure_paths(PROJECT_ROOT)
    # Keep the smoke harness deliberately smaller than the application builder:
    # one metadata reset, followed by the adapter-controlled policy/reset order.
    from robot_agent.environments import RobosuiteBackend

    semantic, grid_file = _choose_map_files(PROJECT_ROOT, args.task_index)
    scene_data, grid = load_map_files(semantic, grid_file)
    scene = SceneContext.from_semantic_map(scene_data)
    print(json.dumps({"phase": "create_backend", "task": task["level"]}), flush=True)
    backend = RobosuiteBackend(
        env_name=task["env_name"],
        camera="birdview",
        drive_mode="direct",
    )
    backend.reset()
    print(json.dumps({"phase": "metadata_reset_complete"}), flush=True)
    skills = {
        skill.name: skill
        for skill in wired_skills(
            backend,
            scene_context=scene,
            grid=grid,
            path_spacing=0.35,
        )
    }
    print(json.dumps({"phase": "adapter_reset_complete"}), flush=True)
    results: list[dict] = []
    objects_completed = 0
    try:
        for object_name in objects:
            results.append(
                _run_skill(skills, "move", {"target": task["source"]})
            )
            if not results[-1]["success"]:
                return 2
            results.append(
                _run_skill(
                    skills,
                    "pick_up",
                    {"target": task["source"], "object_name": object_name},
                )
            )
            if not results[-1]["success"]:
                return 3
            if not (args.through_place or args.all_objects):
                return 0
            results.append(
                _run_skill(skills, "move", {"target": task["target"]})
            )
            if not results[-1]["success"]:
                return 4
            results.append(
                _run_skill(skills, "place_down", {"target": task["target"]})
            )
            if not results[-1]["success"]:
                return 5
            objects_completed += 1
        return 0
    finally:
        close = getattr(backend, "close", None)
        if callable(close):
            close()
        print(
            json.dumps(
                {
                    "summary": {
                        "task": task["level"],
                        "steps": len(results),
                        "objects_requested": len(objects),
                        "objects_completed": objects_completed,
                        "all_success": bool(results)
                        and all(item["success"] for item in results),
                        "total_step_seconds": round(
                            sum(item["elapsed_seconds"] for item in results), 3
                        ),
                    }
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
