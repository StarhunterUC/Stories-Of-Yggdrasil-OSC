"""Read-only ordering guard for asynchronously received Sam.py state snapshots.

This module does not change server revisions or mutate game state.
"""
from __future__ import annotations

from typing import Any


def stale_same_character_revision(
    incoming: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> bool:
    """True only if the new state is older for the SAME linked player character.

    Revisions belong to the Sam.py character's OSC metadata, not the Desktop
    process. A different player or changed linked character may legitimately
    start with a lower revision, so those transitions are never blocked.
    """
    if not isinstance(incoming, dict) or not isinstance(current, dict):
        return False
    incoming_user = str(incoming.get("user_id") or "").strip()
    current_user = str(current.get("user_id") or "").strip()
    incoming_character = str(incoming.get("linked_character") or "").strip()
    current_character = str(current.get("linked_character") or "").strip()
    if not (incoming_user and current_user and incoming_character and current_character):
        return False
    if incoming_user != current_user or incoming_character != current_character:
        return False
    try:
        incoming_revision = int(incoming["revision"])
        current_revision = int(current["revision"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return incoming_revision < current_revision
