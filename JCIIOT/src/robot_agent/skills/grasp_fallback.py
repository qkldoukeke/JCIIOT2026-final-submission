"""Deprecated compatibility API for the removed skill-layer MuJoCo fallback.

Physical grasp execution now belongs to ``EnvBackend.grasp_object_physics``.
These functions remain importable for old offline diagnostics, but deliberately
do not unwrap environments, copy simulator state, or patch collector helpers.
"""

from __future__ import annotations


def sync_material_object_states(_source_env, _destination_env) -> int:
    """State synchronization is intentionally owned by EnvBackend."""
    return 0


def run_dynamic_scripted_grasp(
    _env,
    object_name: str,
    render: bool = False,
    nav_env=None,
) -> dict:
    """Return a fail-closed result instead of touching MuJoCo from a skill."""
    del render, nav_env
    return {
        "success": False,
        "successes": 0,
        "num_rollouts": 0,
        "return": 0.0,
        "scripted_fallback": False,
        "object_name": object_name,
        "reason": (
            "skill-layer scripted fallback disabled; use "
            "EnvBackend.grasp_object_physics"
        ),
    }

