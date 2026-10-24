"""Read-only presentation helpers for Sam.py combat profiles and active effects.

These helpers do not mutate HP, gameplay statuses, NPC records, or combat stats.
"""
from __future__ import annotations

from collections.abc import KeysView
import math
import time
from typing import Any

STAT_KEYS = ("ATK", "DEF", "MAG", "RES", "SPD", "EVA", "VIT")
CORE_STAT_KEYS = STAT_KEYS[:-1]


def _status_name(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("name") or entry.get("status") or entry.get("effect") or "").strip()
    return str(entry or "").strip()


def _number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool) or str(value).strip() == "":
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _remaining_text(seconds: int) -> str:
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    if seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"


def active_effect_labels(
    character: dict[str, Any] | None,
    *,
    now: float | None = None,
    offline_statuses: Any = (),
) -> list[str]:
    """Render ALL names in authoritative status_effects/status_names, not five UI slots.

    If the server supplies timestamps, display remaining time without generating
    client-owned timers. The server remains authoritative for expiration.
    """
    char = character if isinstance(character, dict) else {}
    timestamp = time.time() if now is None else float(now)
    shown: dict[str, str] = {}
    expired: set[str] = set()
    entries = char.get("status_effects")
    if isinstance(entries, dict):
        # Some server builds serialize status effects as a mapping keyed by name.
        entries = [
            dict(details, name=details.get("name") or str(name))
            if isinstance(details, dict) else {"name": str(name), "active": bool(details)}
            for name, details in entries.items()
        ]
    elif not isinstance(entries, list):
        entries = []
    for item in entries:
        name = _status_name(item)
        if not name:
            continue
        key = name.casefold()
        info = item if isinstance(item, dict) else {}
        if info.get("active") is False:
            continue
        expires_at = _number(info.get("expires_at"))
        if expires_at is not None and expires_at > 0 and expires_at <= timestamp:
            expired.add(key)
            continue
        parts = [name]
        if expires_at is not None and expires_at > timestamp:
            parts.append(_remaining_text(max(1, math.ceil(expires_at - timestamp))))
        else:
            seconds = _number(info.get("remaining_seconds", info.get("duration_remaining")))
            if seconds is not None and seconds > 0:
                parts.append(_remaining_text(max(1, math.ceil(seconds))))
        stacks = _number(info.get("stacks"))
        if stacks is not None and stacks > 1:
            parts.append(f"x{int(stacks)}")
        potency = _number(info.get("potency"))
        if potency is not None and potency > 1:
            parts.append(f"Potency {int(potency)}")
        shown[key] = " · ".join(parts)

    names = char.get("status_names")
    if isinstance(names, (list, tuple, set)):
        for item in names:
            name = _status_name(item)
            if name and name.casefold() not in expired:
                shown.setdefault(name.casefold(), name)

    # Local statuses are only a display fallback when no server character exists.
    # Never mix an old Player's local effects into a confirmed NPC's status list.
    if not char:
        local_names = offline_statuses.keys() if isinstance(offline_statuses, dict) else offline_statuses
        if isinstance(local_names, (list, tuple, set, KeysView)):
            for item in local_names:
                name = _status_name(item)
                if name:
                    shown.setdefault(name.casefold(), name)

    return [shown[key] for key in sorted(shown)]


def _stat_value(stats: dict[str, Any], key: str) -> int | None:
    raw = stats.get(key, stats.get(key.casefold()))
    number = _number(raw)
    return int(number) if number is not None else None


def _format_stats(stats: dict[str, Any]) -> str:
    return "  •  ".join(
        f"{key} {value if (value := _stat_value(stats, key)) is not None else '—'}"
        for key in STAT_KEYS
    )


def combat_stats_display(
    profile: dict[str, Any] | None,
    character: dict[str, Any] | None,
    npc_roster: list[dict[str, Any]] | None,
    profile_mode: str,
) -> tuple[str, str]:
    """Return display text and optional discrepancy warning, without stat mutations."""
    data = profile if isinstance(profile, dict) else {}
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    rendered = _format_stats(stats)
    if str(profile_mode or "").casefold() != "npc":
        return rendered, ""

    char = character if isinstance(character, dict) else {}
    char_name = str(char.get("name") or "").strip().casefold()
    if not char_name:
        return rendered, ""
    row = next((
        item for item in (npc_roster or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip().casefold() == char_name
    ), None)
    if not row:
        return rendered, ""

    effective_is_zero = all((_stat_value(stats, key) or 0) == 0 for key in CORE_STAT_KEYS)
    roster_has_real_stats = any((_stat_value(row, key) or 0) > 0 for key in CORE_STAT_KEYS)
    if effective_is_zero and roster_has_real_stats:
        return (
            _format_stats(row),
            "NPC ROSTER REFERENCE ONLY — Sam.py's effective combat profile returned zeros or no stats. "
            "Damage still uses server authority; this display does not correct combat calculations.",
        )
    return rendered, ""
