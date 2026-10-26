"""Safe, opt-in movement lock projection from authoritative Sam.py state.

The server owns the effect list. Never infer immobilization from raw Contacts,
unknown PvP sources or client-side visual effects.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MOVEMENT_PARAMETER = "SoY_MovementLocked"
IMMOBILIZING_EFFECTS = frozenset({
    "freeze", "frozen", "bind", "bound", "immobilize", "immobilized",
    "stun", "stunned", "petrify", "petrified", "paralyze", "paralysis",
    "sleep", "asleep",
})


def movement_locked_from_sam_state(state: Mapping[str, Any] | None) -> bool:
    """Return True only for an explicit authoritative immobilizing status.

    A missing/invalid payload fails OPEN for movement, never leaving VRChat
    locomotion disabled based on stale local context.
    """
    if not isinstance(state, Mapping):
        return False
    char = state.get("character")
    if not isinstance(char, Mapping):
        return False
    names = char.get("status_names")
    if not isinstance(names, (list, tuple, set, frozenset)):
        return False
    return any(str(name or "").strip().casefold() in IMMOBILIZING_EFFECTS for name in names)
