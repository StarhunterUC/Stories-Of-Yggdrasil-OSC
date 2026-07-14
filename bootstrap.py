from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQ = BASE / "requirements.txt"
MARKER = VENV / ".stories_osc_requirements.sha256"


def run(*args: str) -> None:
    subprocess.check_call(list(args), cwd=BASE)


def main() -> int:
    if not PYTHON.exists():
        print("[Stories OSC] Preparing the local environment…")
        run(sys.executable, "-m", "venv", str(VENV))
    digest = hashlib.sha256(REQ.read_bytes()).hexdigest()
    installed = MARKER.read_text(encoding="utf-8").strip() if MARKER.exists() else ""
    if installed != digest:
        print("[Stories OSC] Installing or updating required components…")
        run(str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip")
        run(str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQ))
        MARKER.write_text(digest, encoding="utf-8")
    if "--prepare-only" in sys.argv:
        print("[Stories OSC] Environment ready.")
        return 0
    print("[Stories OSC] Launching…")
    return subprocess.call([str(PYTHON), str(BASE / "main.py")], cwd=BASE)


if __name__ == "__main__":
    raise SystemExit(main())
