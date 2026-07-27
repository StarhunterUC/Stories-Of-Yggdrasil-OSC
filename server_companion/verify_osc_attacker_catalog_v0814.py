#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

PATCH_VERSION = "0.8.14-npc-attacker-catalog"


def main() -> int:
    path = Path("/opt/sam/admin_server.py")
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    checks = {
        "API version 0.8.14": bool(re.search(r'STORIES_OSC_API_VERSION\s*=\s*["\']0\.8\.14["\']', source)),
        "patch marker": f'OSC_ATTACKER_CATALOG_PATCH_VERSION = "{PATCH_VERSION}"' in source,
        "attacker response": '"attackers": attackers' in source,
        "metadata filter": 'if not uid.isdigit()' in source,
        "KO eligibility": '"eligible": eligible' in source,
        "read-only stat snapshot": '_combat_stats_snapshot' in source,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if failed:
        raise AssertionError(", ".join(failed))
    print("OSC attacker catalog v0.8.14 verification passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"VERIFY FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
