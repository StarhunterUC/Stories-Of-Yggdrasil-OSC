#!/usr/bin/env python3
"""Add a read-only Player -> NPC attacker catalog to the live OSC API.

This companion patch targets the currently deployed v0.8.13 OSC API. It does
not replace Sam.py or the OSC bridge. It updates only admin_server.py, creates a
timestamped backup, compiles the result, and can restart sam.service.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PATCH_VERSION = "0.8.14-npc-attacker-catalog"
PREVIOUS_API_VERSION = "0.8.13"
API_VERSION = "0.8.14"

ATTACKER_CATALOG_HELPER = r'''
def _stories_osc_attacker_catalog(players: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Return safe, read-only attacker identities and current stat previews.

    Only numeric Discord user records and real character dictionaries are
    included. Metadata entries such as ``dump`` are ignored. The preview is
    informational; Player -> NPC damage still recalculates the selected
    character server-side when the hit is resolved.
    """
    try:
        from core import osc_sam_bridge as _osc_bridge
        snapshot_fn = getattr(_osc_bridge, "_combat_stats_snapshot", None)
    except Exception:
        snapshot_fn = None

    def _to_int(value: Any, default: int = 0, minimum: int = 0) -> int:
        try:
            return max(minimum, int(float(str(value).strip())))
        except Exception:
            return max(minimum, int(default or 0))

    def _status_names(char: Dict[str, Any]) -> set[str]:
        names: set[str] = set()
        raw_names = char.get("status_names")
        if isinstance(raw_names, list):
            names.update(str(value).strip().casefold() for value in raw_names if str(value).strip())
        raw = char.get("status_effects")
        if isinstance(raw, dict):
            names.update(str(key).strip().casefold() for key, value in raw.items() if value and str(key).strip())
        elif isinstance(raw, list):
            for value in raw:
                if isinstance(value, dict):
                    name = str(value.get("name") or value.get("status") or "").strip()
                else:
                    name = str(value).strip()
                if name:
                    names.add(name.casefold())
        return names

    rows: list[Dict[str, Any]] = []
    if not isinstance(players, dict):
        return rows

    for raw_uid, pdata in players.items():
        uid = str(raw_uid or "").strip()
        if not uid.isdigit() or not isinstance(pdata, dict):
            continue
        chars = pdata.get("characters") if isinstance(pdata.get("characters"), dict) else {}
        active = str(pdata.get("active") or pdata.get("active_character") or pdata.get("active_char") or "").strip()
        account_name = str(
            pdata.get("display_name")
            or pdata.get("discord_name")
            or pdata.get("username")
            or pdata.get("user_name")
            or f"Discord {uid}"
        ).strip()
        player_label = f"{account_name} — {uid}" if uid not in account_name else account_name

        for raw_name, char in chars.items():
            if not isinstance(char, dict):
                continue
            char_name = str(char.get("name") or raw_name or "").strip()
            if not char_name:
                continue
            try:
                preview = dict(snapshot_fn(char)) if callable(snapshot_fn) else {}
            except Exception:
                preview = {}

            level = _to_int(preview.get("level", char.get("level", 1)), 1, 1)
            max_hp = _to_int(preview.get("max_hp", char.get("max_hp", char.get("hp", 1))), 1, 1)
            hp = min(max_hp, _to_int(char.get("hp", preview.get("hp", max_hp)), max_hp, 0))
            statuses = _status_names(char)
            eligible = hp > 0 and "ko" not in statuses and "dead" not in statuses
            unavailable_reason = "" if eligible else "Character is KO and cannot attack."

            classes = char.get("classes") if isinstance(char.get("classes"), list) else []
            class_names = [str(value).strip() for value in classes if str(value).strip() and str(value).strip().casefold() != "none"]
            if not class_names:
                fallback_class = str(char.get("class") or char.get("primary_class") or "").strip()
                if fallback_class:
                    class_names = [fallback_class]

            rows.append({
                "user_id": uid,
                "account_name": account_name,
                "player_label": player_label,
                "character_name": char_name,
                "active": char_name.casefold() == active.casefold() if active else False,
                "eligible": eligible,
                "unavailable_reason": unavailable_reason,
                "level": level,
                "hp": hp,
                "max_hp": max_hp,
                "atk": _to_int(preview.get("atk", char.get("atk", char.get("attack", 0))), 0, 0),
                "mag": _to_int(preview.get("mag", char.get("mag", char.get("magic", 0))), 0, 0),
                "spd": _to_int(preview.get("spd", char.get("spd", char.get("speed", 0))), 0, 0),
                "classes": class_names,
                "race": str(char.get("race") or "Unknown"),
                "region": str(char.get("region") or "Unknown"),
            })

    rows.sort(key=lambda row: (
        str(row.get("player_label") or "").casefold(),
        0 if bool(row.get("active", False)) else 1,
        str(row.get("character_name") or "").casefold(),
    ))
    return rows
'''.strip()

NPC_CATALOG_ROUTE = r'''
async def stories_osc_npc_catalog(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    _stories_osc_link_from_auth(authorization)
    roster = osc_list_npc_roster()
    attackers = _stories_osc_attacker_catalog(_stories_osc_live_players())
    return {
        "ok": True,
        "enemies": roster,
        "count": len(roster),
        "attackers": attackers,
        "attacker_count": len(attackers),
        "capabilities": {
            "npc_verified_attacker": True,
            "npc_attacker_catalog": True,
            "npc_damage_diagnostics": True,
            "npc_hp_independent_damage": True,
        },
        "api_version": STORIES_OSC_API_VERSION,
    }
'''.strip()


def _top_level_function(source: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one top-level {name}(); found {len(matches)}")
    return matches[0]


def _replace_function(source: str, name: str, replacement: str) -> str:
    node = _top_level_function(source, name)
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = int(node.end_lineno or node.lineno)
    return "".join(lines[:start]) + replacement.rstrip() + "\n\n" + "".join(lines[end:])


def patch_admin(source: str) -> str:
    if f'OSC_ATTACKER_CATALOG_PATCH_VERSION = "{PATCH_VERSION}"' in source:
        return source

    version_pattern = re.compile(r'(?m)^(STORIES_OSC_API_VERSION\s*=\s*)["\']([^"\']+)["\']\s*$')
    matches = list(version_pattern.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one STORIES_OSC_API_VERSION assignment; found {len(matches)}")
    current = matches[0].group(2)
    if current != PREVIOUS_API_VERSION:
        raise RuntimeError(f"Expected OSC API {PREVIOUS_API_VERSION}; found {current}")
    source = version_pattern.sub(rf'\1"{API_VERSION}"', source, count=1)

    route_decorator = '@app.get("/api/osc/npc/catalog")'
    marker_at = source.find(route_decorator)
    if marker_at < 0:
        raise RuntimeError("Could not locate /api/osc/npc/catalog route")
    helper_block = (
        f'OSC_ATTACKER_CATALOG_PATCH_VERSION = "{PATCH_VERSION}"\n\n'
        + ATTACKER_CATALOG_HELPER
        + "\n\n"
    )
    source = source[:marker_at] + helper_block + source[marker_at:]
    source = _replace_function(source, "stories_osc_npc_catalog", NPC_CATALOG_ROUTE)
    compile(source, "admin_server.py", "exec")
    return source


def _fixture_test() -> None:
    namespace: dict[str, object] = {"Dict": dict, "Any": object}
    exec(ATTACKER_CATALOG_HELPER, namespace)
    helper = namespace["_stories_osc_attacker_catalog"]
    players = {
        "dump": {"metadata": True},
        "not-a-user": {"characters": {"Ghost": {"hp": 999}}},
        "123": {
            "display_name": "Akira",
            "active": "Clover",
            "characters": {
                "Clover": {"name": "Clover", "level": 30, "hp": 900, "max_hp": 1000, "atk": 75},
                "KO": {"name": "KO", "level": 10, "hp": 0, "max_hp": 400},
            },
        },
    }
    rows = helper(players)  # type: ignore[operator]
    assert len(rows) == 2, rows
    assert all(row["user_id"] == "123" for row in rows)
    assert next(row for row in rows if row["character_name"] == "Clover")["eligible"] is True
    assert next(row for row in rows if row["character_name"] == "KO")["eligible"] is False


def validate(source: str) -> None:
    required = [
        f'STORIES_OSC_API_VERSION = "{API_VERSION}"',
        f'OSC_ATTACKER_CATALOG_PATCH_VERSION = "{PATCH_VERSION}"',
        '"attackers": attackers',
        '"npc_attacker_catalog": True',
        'if not uid.isdigit()',
        'snapshot_fn = getattr(_osc_bridge, "_combat_stats_snapshot", None)',
    ]
    for marker in required:
        if marker not in source:
            raise RuntimeError(f"Missing validation marker: {marker}")
    compile(source, "admin_server.py", "exec")
    _fixture_test()


def atomic_write(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".v0814.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/opt/sam")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    admin_path = root / "admin_server.py"
    if not admin_path.exists():
        raise FileNotFoundError(f"Missing {admin_path}")

    original = admin_path.read_text(encoding="utf-8")
    patched = patch_admin(original)
    validate(patched)

    if args.dry_run:
        print(f"DRY RUN OK — {PATCH_VERSION}")
        print("  [OK] OSC API will become 0.8.14")
        print("  [OK] Numeric Discord player records only")
        print("  [OK] Metadata entries such as dump are excluded")
        print("  [OK] KO characters remain visible but ineligible")
        print("  [OK] Stat previews are read-only and never trusted for damage")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / "backups" / f"osc-attacker-catalog-v0814-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(admin_path, backup / "admin_server.py")

    try:
        atomic_write(admin_path, patched)
        subprocess.run(
            [str(root / ".venv" / "bin" / "python"), "-m", "py_compile", str(admin_path)],
            cwd=str(root),
            check=True,
        )
        if args.restart:
            subprocess.run(["systemctl", "restart", "sam.service"], check=True)
            subprocess.run(["systemctl", "is-active", "--quiet", "sam.service"], check=True)
    except Exception:
        shutil.copy2(backup / "admin_server.py", admin_path)
        if args.restart:
            subprocess.run(["systemctl", "restart", "sam.service"], check=False)
        raise

    print(f"PATCHED — {PATCH_VERSION}")
    print(f"Backup: {backup}")
    print("  [OK] /api/osc/npc/catalog now includes attacker rows")
    print("  [OK] sam.service restarted and is active" if args.restart else "  [OK] Files patched; service not restarted")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PATCH FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
