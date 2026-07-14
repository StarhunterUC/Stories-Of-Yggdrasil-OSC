from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def vrchat_osc_root() -> Path:
    """Return VRChat's normal Windows OSC config root."""
    user_profile = Path(os.getenv("USERPROFILE", Path.home()))
    return user_profile / "AppData" / "LocalLow" / "VRChat" / "VRChat" / "OSC"


def find_avatar_config(avatar_id: str) -> Path | None:
    avatar_id = str(avatar_id or "").strip()
    if not avatar_id or avatar_id == "—":
        return None
    root = vrchat_osc_root()
    if not root.exists():
        return None
    matches = list(root.glob(f"*/Avatars/{avatar_id}.json"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def inspect_avatar_config(path: Path, required_parameters: list[str]) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("parameters", []) if isinstance(raw, dict) else []
    by_name = {
        str(item.get("name")): item
        for item in entries
        if isinstance(item, dict) and item.get("name")
    }
    details: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    missing_output: list[str] = []
    for name in required_parameters:
        entry = by_name.get(name)
        if entry is None:
            missing.append(name)
            continue
        output = entry.get("output") if isinstance(entry.get("output"), dict) else None
        details[name] = {
            "input": entry.get("input"),
            "output": output,
        }
        if not output or not output.get("address"):
            missing_output.append(name)
    return {
        "path": str(path),
        "avatar_id": raw.get("id") if isinstance(raw, dict) else None,
        "avatar_name": raw.get("name") if isinstance(raw, dict) else None,
        "parameter_count": len(by_name),
        "missing": missing,
        "missing_output": missing_output,
        "details": details,
        "ok": not missing and not missing_output,
    }
