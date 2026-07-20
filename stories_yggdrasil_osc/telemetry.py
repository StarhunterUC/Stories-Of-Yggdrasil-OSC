from __future__ import annotations

import math
from typing import Any


def coerce_percent(value: Any) -> float:
    """Return a finite percentage clamped to 0..100."""
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(raw):
        return 0.0
    return max(0.0, min(100.0, raw))


def percent_to_avatar_float(value: Any) -> float:
    """VRChat radial Float parameters use a normalized 0..1 value."""
    return coerce_percent(value) / 100.0


def diablos_warning_label(percent: Any) -> str:
    value = coerce_percent(percent)
    if value >= 98:
        return "CRITICAL — Possession imminent"
    if value >= 90:
        return "Severe warning"
    if value >= 50:
        return "High warning"
    if value >= 25:
        return "Warning"
    return "Stable"
