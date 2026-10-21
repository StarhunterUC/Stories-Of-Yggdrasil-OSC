"""Safety checks for switching device-scoped NPC combat profiles."""
from __future__ import annotations

from typing import Any


def confirmed_npc(state: dict[str, Any], npc_cfg: dict[str, Any]) -> bool:
    """Require both server NPC mode and the exact roster key."""
    npc = state.get("npc") if isinstance(state.get("npc"), dict) else {}
    key = str(npc_cfg.get("enemy_key") or "").strip()
    return bool(
        key and npc_cfg.get("enabled") is True
        and str(state.get("profile_mode") or "").casefold() == "npc"
        and str(npc.get("enemy_key") or "").strip() == key
    )


def passive_hp_sync_allowed(state: dict[str, Any], npc_cfg: dict[str, Any]) -> bool:
    """Never copy the previous runtime HP into another profile via /sync."""
    return not bool(npc_cfg.get("enabled")) and str(state.get("profile_mode") or "player").casefold() != "npc"


def npc_restore_payload(
    state: dict[str, Any], npc_cfg: dict[str, Any], *,
    client_seq: int, client_session: str, client_version: str,
) -> dict[str, Any]:
    """Build intentional NPC session healing through existing authenticated /sync."""
    if not confirmed_npc(state, npc_cfg):
        raise ValueError("Sam.py has not acknowledged the selected NPC runtime.")
    char = state.get("character") if isinstance(state.get("character"), dict) else {}
    try:
        hp, maximum = int(char["hp"]), int(char["max_hp"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("NPC HP is not available from Sam.py.") from exc
    if maximum < 1 or hp < 0 or hp >= maximum:
        raise ValueError("NPC HP is already full or the profile is invalid.")
    if not str(client_session).strip():
        raise ValueError("Desktop session is not initialized.")
    return {
        "client_seq": int(client_seq),
        "client_session": str(client_session),
        "client_version": str(client_version),
        "client_event": "npc_restore_hp",
        "vrc_trigger": False,
        "npc_mode": True,
        "npc_enemy_key": str(npc_cfg["enemy_key"]),
        "hp": maximum,
        "hp_ratio": 1.0,
    }


def restored_state_matches(state: dict[str, Any], *, key: str) -> bool:
    """A 200 response alone is not evidence of an applied NPC restoration."""
    npc = state.get("npc") if isinstance(state.get("npc"), dict) else {}
    char = state.get("character") if isinstance(state.get("character"), dict) else {}
    sync = state.get("sync_result") if isinstance(state.get("sync_result"), dict) else {}
    try:
        hp, maximum = int(char["hp"]), int(char["max_hp"])
    except (KeyError, ValueError, TypeError):
        return False
    return bool(
        key and str(state.get("profile_mode") or "").casefold() == "npc"
        and str(npc.get("enemy_key") or "") == key
        and maximum >= 1 and hp == maximum
        and not bool(sync.get("duplicate", False))
        and bool(sync.get("accepted", True))
    )
