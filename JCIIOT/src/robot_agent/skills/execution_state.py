"""Skill-owned execution state without concrete-backend introspection.

The official ``EnvBackend`` protocol does not expose implementation fields such
as ``_held_crate_name`` or ``_physics_checkpoint``.  Keep the small amount of
cross-skill state required by move / place in this module instead of reaching
through the backend abstraction.
"""

from __future__ import annotations

from weakref import WeakKeyDictionary


_HELD_OBJECTS: WeakKeyDictionary = WeakKeyDictionary()
_CONFIGURED_CHECKPOINTS: WeakKeyDictionary = WeakKeyDictionary()
_PLACED_OBJECTS: WeakKeyDictionary = WeakKeyDictionary()


def set_held_object(backend, object_name: str | None) -> None:
    if object_name:
        _HELD_OBJECTS[backend] = str(object_name)
    else:
        _HELD_OBJECTS.pop(backend, None)


def held_object(backend) -> str | None:
    value = _HELD_OBJECTS.get(backend)
    return str(value) if value else None


def configured_checkpoint(backend) -> str | None:
    value = _CONFIGURED_CHECKPOINTS.get(backend)
    return str(value) if value else None


def set_configured_checkpoint(backend, checkpoint: str) -> None:
    _CONFIGURED_CHECKPOINTS[backend] = str(checkpoint)


def mark_placed_object(backend, object_name: str | None) -> None:
    if not object_name:
        return
    placed = set(_PLACED_OBJECTS.get(backend, set()))
    placed.add(str(object_name))
    _PLACED_OBJECTS[backend] = placed


def placed_objects(backend) -> set[str]:
    return set(_PLACED_OBJECTS.get(backend, set()))
