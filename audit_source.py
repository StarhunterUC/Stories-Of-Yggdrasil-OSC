from __future__ import annotations

import json
from pathlib import Path

from stories_yggdrasil_osc import __version__

ROOT = Path(__file__).resolve().parent
metadata = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))

expected = "0.8.11"
if __version__ != expected:
    raise SystemExit(f"Package version mismatch: {__version__!r} != {expected!r}")
if str(metadata.get("version")) != expected:
    raise SystemExit(f"version.json mismatch: {metadata.get('version')!r} != {expected!r}")
if not (ROOT / "Stories Of Yggdrasil OSC.spec").is_file():
    raise SystemExit("PyInstaller spec file is missing.")
if not (ROOT / "assets" / "stories_osc_icon.ico").is_file():
    raise SystemExit("Application icon is missing.")

print("Stories Of Yggdrasil OSC Desktop source audit passed.")
print(f"Desktop version: {expected}")
print(f"OSC API minimum: {metadata.get('api_minimum')}")
print(f"OSC API recommended: {metadata.get('api_recommended')}")
print(f"Unity Tool: {metadata.get('unity_tool')}")

required_markers = {
    "stories_yggdrasil_osc/app.py": ["npc_attacker_user_id", "Player → NPC Damage Attacker", "OSC_API_MINIMUM"],
    "stories_yggdrasil_osc/config.py": ["attacker_mode", "attacker_user_id", "attacker_char_name"],
    "contracts/OSC_CONTRACT_v15.json": ["verified_attacker_identity"],
}
for relative, markers in required_markers.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"Missing v0.8.11 marker {marker!r} in {relative}")
print("Verified Player → NPC attacker identity support is present.")
