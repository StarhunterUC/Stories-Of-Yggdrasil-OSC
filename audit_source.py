from __future__ import annotations

import json
from pathlib import Path

from stories_yggdrasil_osc import __version__

ROOT = Path(__file__).resolve().parent
metadata = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))

expected = "0.8.14"
if __version__ != expected:
    raise SystemExit(f"Package version mismatch: {__version__!r} != {expected!r}")
if str(metadata.get("version")) != expected:
    raise SystemExit(f"version.json mismatch: {metadata.get('version')!r} != {expected!r}")
if not (ROOT / "Stories Of Yggdrasil OSC.spec").is_file():
    raise SystemExit("PyInstaller spec file is missing.")
if not (ROOT / "assets" / "stories_osc_icon.ico").is_file():
    raise SystemExit("Application icon is missing.")

required_markers = {
    "main.py": ["app_v0814"],
    "stories_yggdrasil_osc/app_v0814.py": [
        "Reconnect All",
        "Quick Actions",
        "Create Support Bundle",
        "action_favorites",
        "npc_favorites",
        "StripOn.TLabel",
    ],
    "stories_yggdrasil_osc/qol.py": [
        "build_action_catalog",
        "append_grouped_activity",
        "create_support_bundle",
        "redact_sensitive",
        "should_suppress_activity_repeat",
    ],
    "stories_yggdrasil_osc/config.py": [
        '"version": 18',
        '"window_geometry"',
        '"action_favorites"',
        '"npc_favorites"',
    ],
    "contracts/OSC_CONTRACT_v15.json": ["verified_attacker_identity"],
}
for relative, markers in required_markers.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"Missing v0.8.14 marker {marker!r} in {relative}")

print("Stories Of Yggdrasil OSC Desktop source audit passed.")
print(f"Desktop version: {expected}")
print(f"OSC API minimum: {metadata.get('api_minimum')}")
print(f"OSC API recommended: {metadata.get('api_recommended')}")
print(f"Unity Tool: {metadata.get('unity_tool')}")
print("Persistent UI state, action favorites, activity grouping, encounter-cleanup suppression, NPC favorites, and sanitized support bundles are present.")
