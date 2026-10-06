#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import subprocess
import sys

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
CONST_RE = {
    "api_minimum": re.compile(r'^OSC_API_MINIMUM\s*=\s*["\']([^"\']+)["\']', re.MULTILINE),
    "api_recommended": re.compile(r'^OSC_API_RECOMMENDED\s*=\s*["\']([^"\']+)["\']', re.MULTILINE),
}


def _version_tuple(value: str) -> tuple[int, int, int]:
    if not SEMVER_RE.fullmatch(value):
        raise ValueError(f"not semantic X.Y.Z: {value!r}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _git_paths(root: Path) -> list[str]:
    if not (root / ".git").exists():
        return []
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Stories Of Yggdrasil OSC Desktop repository before build/release.")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    errors: list[str] = []

    version_path = root / "version.json"
    if not version_path.is_file():
        raise SystemExit("VERIFY FAILED: missing version.json")

    try:
        metadata = json.loads(version_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"VERIFY FAILED: invalid version.json: {exc}") from exc

    product = str(metadata.get("product") or "").strip()
    version = str(metadata.get("version") or "").strip()
    tag = str(metadata.get("tag") or (f"v{version}" if version else "")).strip()
    release_notes = str(metadata.get("release_notes") or (f"PATCH_NOTES_v{version}.md" if version else "")).strip()

    if product != "Stories Of Yggdrasil OSC":
        _fail(errors, f"unexpected product name in version.json: {product!r}")

    try:
        version_tuple = _version_tuple(version)
    except ValueError as exc:
        _fail(errors, f"version.json version is invalid: {exc}")
        version_tuple = (0, 0, 0)

    if tag != f"v{version}":
        _fail(errors, f"release tag must be v<version>: expected v{version}, got {tag!r}")

    required = [
        "main.py",
        "bootstrap.py",
        "requirements.txt",
        "requirements-build.txt",
        "Stories Of Yggdrasil OSC.spec",
        "audit_source.py",
        "README.md",
        "QUICK_START.md",
        "CHANGELOG.md",
        "stories_yggdrasil_osc/__init__.py",
        "contracts/SPELL_ID_REGISTRY_v2.json",
        "contracts/TECHNICK_ID_REGISTRY_v1.json",
        "contracts/ITEM_ID_REGISTRY_v1.json",
    ]
    for relative in required:
        if not (root / relative).is_file():
            _fail(errors, f"missing required repository file: {relative}")

    notes_path = root / release_notes
    if not release_notes or not notes_path.is_file():
        _fail(errors, f"missing current release notes: {release_notes or '<unset>'}")

    init_path = root / "stories_yggdrasil_osc" / "__init__.py"
    if init_path.is_file():
        init_text = init_path.read_text(encoding="utf-8-sig")
        match = VERSION_RE.search(init_text)
        package_version = match.group(1).strip() if match else ""
        if package_version != version:
            _fail(errors, f"package __version__ {package_version!r} does not match version.json {version!r}")

        for metadata_key, pattern in CONST_RE.items():
            expected = str(metadata.get(metadata_key) or "").strip()
            if not expected:
                continue
            const = pattern.search(init_text)
            actual = const.group(1).strip() if const else ""
            if actual != expected:
                _fail(errors, f"{metadata_key} mismatch: version.json={expected!r}, package={actual!r}")

    # v0.8.21 introduced the coordinated Unity Tool TB16 / OSC Protocol 19 gate.
    # Refuse to publish a v0.8.21+ tree that only had its version string bumped.
    if version_tuple >= (0, 8, 21):
        protocol = metadata.get("osc_protocol_version")
        if not isinstance(protocol, int) or protocol < 19:
            _fail(errors, "v0.8.21+ requires integer osc_protocol_version >= 19 in version.json")

        if version_tuple == (0, 8, 21):
            if protocol != 19:
                _fail(errors, f"v0.8.21 must publish OSC Protocol 19, received {protocol!r}")
            if str(metadata.get("unity_tool") or "").strip() != "0.5.10-TB16":
                _fail(errors, "v0.8.21 must declare unity_tool '0.5.10-TB16'")

        source_text = "\n".join(
            path.read_text(encoding="utf-8-sig", errors="replace")
            for path in sorted((root / "stories_yggdrasil_osc").glob("*.py"))
        )
        for marker in (
            "SoY_UnityToolPresent",
            "SoY_ProtocolVersion",
            "SoY_UnitySchemaValid",
        ):
            if marker not in source_text:
                _fail(errors, f"v0.8.21+ Protocol 19 source marker missing: {marker}")

    tracked = _git_paths(root)
    if tracked:
        forbidden_prefixes = ("build/", "dist/", "release/", ".venv/", ".pytest_cache/", "backups/")
        forbidden_suffixes = (".pyc", ".pyo")
        bad = [
            p for p in tracked
            if p.startswith(forbidden_prefixes)
            or p.endswith(forbidden_suffixes)
            or "/__pycache__/" in f"/{p}/"
            or (p.startswith("Stories_Of_Yggdrasil_OSC_Windows_") and (p.endswith(".zip") or p.endswith(".sha256")))
        ]
        if bad:
            _fail(errors, "generated/local files are tracked: " + ", ".join(sorted(bad)[:20]))

    if errors:
        print("VERIFY FAILED", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print("VERIFY PASSED")
    print(f" - product: {product}")
    print(f" - version: {version}")
    print(f" - tag: {tag}")
    print(f" - release_notes: {release_notes}")
    if metadata.get("osc_protocol_version") is not None:
        print(f" - osc_protocol_version: {metadata.get('osc_protocol_version')}")
    if metadata.get("unity_tool"):
        print(f" - unity_tool: {metadata.get('unity_tool')}")
    print(" - repository hygiene: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
