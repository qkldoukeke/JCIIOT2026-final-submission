"""Skill library — wired to a real or simulated backend.

All skills require a backend; there is no mock / no-op fallback.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np

from robot_agent.core.memory import InMemoryStore
from robot_agent.core.scene_context import SceneContext
from robot_agent.environments.base import EnvBackend
from robot_agent.skills.base import BaseSkill
from robot_agent.skills.move import MoveSkill
from robot_agent.skills.pick_up import PickUpSkill, _configure_task_checkpoint
from robot_agent.skills.place_down import PlaceDownSkill
from robot_agent.skills.record_trajectory import RecordTrajectorySkill
from robot_agent.skills.analyze_supply import AnalyzeSupplySkill
from robot_agent.skills.knowledge_mgr import KnowledgeMgrSkill
from robot_agent.skills.memory_mgr import MemoryMgrSkill
from robot_agent.skills.read_document import ReadDocumentSkill
from robot_agent.skills.task_station_mapping import configured_task
from robot_agent.workflows.semantic_backend import SemanticBackendAdapter


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TASK_CONFIG_PATH = _PROJECT_ROOT / "knowledge" / "task_config.json"
_GENERATED_SOPS_ROOT = _PROJECT_ROOT / "team_submission" / "generated_sops"
_TEAM_KNOWLEDGE_ROOT = _PROJECT_ROOT / "team_submission" / "knowledge"
_ACTIVE_SOP_PATH = _TEAM_KNOWLEDGE_ROOT / "current_generated_sop.md"


def _activate_generated_sop_for_scene(
    scene_context: SceneContext | None,
) -> dict | None:
    """Activate the team-generated SOP matching the live environment.

    The environment-to-level mapping remains authoritative in the locked
    ``task_config.json``.  This skill-layer adapter only selects an already
    generated team SOP and copies it into the planner-visible team knowledge
    directory.  It does not alter organizer knowledge or infer coordinates.
    """
    if scene_context is None:
        return None

    scene_name = str(scene_context.scene_name or "").strip()
    map_name = str(scene_context.map_name or "").strip()
    identifiers = {
        value.casefold()
        for value in (
            scene_name,
            map_name,
            map_name.removesuffix("_scene_regenerated"),
        )
        if value
    }
    if not identifiers or not _TASK_CONFIG_PATH.exists():
        return None

    try:
        task = configured_task(scene_context)
        if task is None:
            logger.warning(
                "team SOP activation skipped: scene=%s",
                "/".join(sorted(identifiers)),
            )
            return None

        env_name = str(task.get("env_name") or "")
        level = str(task.get("level") or "").strip().upper()
        source = str(task.get("source") or "").strip()
        target = str(task.get("target") or "").strip()
        generated_path = _GENERATED_SOPS_ROOT / f"generated_sop_{level.lower()}.md"
        if not generated_path.exists():
            logger.warning(
                "team SOP activation skipped: missing %s",
                generated_path,
            )
            return None

        content = generated_path.read_text(encoding="utf-8")
        required_markers = (
            f"CURRENT LEVEL: `{level}`",
            f"Environment: `{env_name}`",
            f"Source station ID: `{source}`",
            f"Target station ID: `{target}`",
        )
        missing = [marker for marker in required_markers if marker not in content]
        if missing:
            raise ValueError(
                "generated SOP failed task binding validation: "
                + ", ".join(missing)
            )

        _TEAM_KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
        current = (
            _ACTIVE_SOP_PATH.read_text(encoding="utf-8")
            if _ACTIVE_SOP_PATH.exists()
            else ""
        )
        changed = current != content
        if changed:
            _ACTIVE_SOP_PATH.write_text(content, encoding="utf-8")

        # Keep planner-visible metadata synchronized with the selected level.
        from robot_agent.core.knowledge_manager import KnowledgeManager

        manager = KnowledgeManager(_TEAM_KNOWLEDGE_ROOT)
        manager.reload()
        for document in manager.list_docs():
            if document.get("source_file") == _ACTIVE_SOP_PATH.name:
                manager.update_doc_meta(
                    document["doc_id"],
                    title=f"{level} Current Team SOP",
                    category="sop",
                    tags=[level, "current", "team-generated", "SOP"],
                )
                break

        result = {
            "level": level,
            "environment": env_name,
            "source": source,
            "target": target,
            "generated_sop": str(generated_path),
            "active_sop": str(_ACTIVE_SOP_PATH),
            "changed": changed,
        }
        logger.info("team-generated SOP active: %s", result)
        return result
    except Exception:
        logger.exception(
            "team-generated SOP activation failed for %s",
            "/".join(sorted(identifiers)),
        )
        return None


def _detect_vision_api_config() -> dict:
    """Detect vision API configuration from environment / robot_params.

    Priority: VLM-specific env vars > OPENAI_* env vars > robot_params.json > defaults.
    """
    cfg: dict = {
        "ollama_base_url": "http://localhost:11434",
        "vision_model": "qwen3-vl:8b",
        "api_type": "ollama",
        "api_key": "",
    }

    # ── Check VLM-specific environment variables first ──
    vlm_url = os.getenv("VLM_BASE_URL", "")
    vlm_key = os.getenv("VLM_API_KEY", "")
    vlm_model = os.getenv("VLM_MODEL", "")
    if vlm_url:
        from robot_agent.core.vision_client import _detect_api_type
        cfg["ollama_base_url"] = vlm_url
        cfg["api_type"] = "openai" if vlm_key else _detect_api_type(vlm_url)
        cfg["api_key"] = vlm_key
        if vlm_model:
            cfg["vision_model"] = vlm_model

    # ── Fallback: OPENAI_* env vars (set when text LLM backend is OpenAI) ──
    elif os.getenv("OPENAI_API_KEY", ""):
        cfg["api_type"] = "openai"
        cfg["api_key"] = os.getenv("OPENAI_API_KEY", "")
        cfg["ollama_base_url"] = os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1",
        )
        openai_model = os.getenv("OPENAI_MODEL", "")
        if openai_model:
            cfg["vision_model"] = openai_model

    # ── Read from robot_params.json for vision-specific settings ──
    try:
        from pathlib import Path
        import json
        _rp = Path(__file__).resolve().parents[3] / "knowledge" / "robot_params.json"
        if _rp.exists():
            _data = json.loads(_rp.read_text(encoding="utf-8"))
            _llm = _data.get("llm", {}) if isinstance(_data, dict) else {}
            if isinstance(_llm, dict):
                if not vlm_url:
                    cfg["ollama_base_url"] = _llm.get(
                        "ollama_base_url", cfg["ollama_base_url"],
                    )
                if not vlm_model:
                    cfg["vision_model"] = _llm.get(
                        "vision_model", cfg["vision_model"],
                    )
    except Exception:
        pass

    return cfg


def wired_skills(
    backend: EnvBackend,
    scene_context: SceneContext,
    grid: np.ndarray,
    *,
    path_spacing: float = 0.35,
    memory_store: InMemoryStore | None = None,
) -> list[BaseSkill]:
    """Return skills wired to a real (or simulated) backend."""
    _activate_generated_sop_for_scene(scene_context)
    _vis_cfg = _detect_vision_api_config()
    execution_backend = SemanticBackendAdapter(backend, scene_context)
    if (
        execution_backend.supports_physics_grasp
        and configured_task(scene_context) is not None
    ):
        _configure_task_checkpoint(execution_backend, scene_context)
    skills: list[BaseSkill] = [
        MoveSkill(
            backend=execution_backend,
            scene_context=scene_context,
            grid=grid,
            path_spacing=path_spacing,
        ),
        PickUpSkill(backend=execution_backend, scene_context=scene_context),
        PlaceDownSkill(backend=execution_backend, scene_context=scene_context),
        AnalyzeSupplySkill(
            backend=execution_backend,
            scene_context=scene_context,
            grid=grid,
            path_spacing=path_spacing,
        ),
        RecordTrajectorySkill(backend=backend),
        KnowledgeMgrSkill(knowledge_root="knowledge"),
        ReadDocumentSkill(
            ollama_base_url=_vis_cfg["ollama_base_url"],
            vision_model=_vis_cfg["vision_model"],
            api_type=_vis_cfg["api_type"],
            api_key=_vis_cfg["api_key"],
        ),
    ]
    if memory_store is not None:
        skills.append(MemoryMgrSkill(store=memory_store))
    return skills
