#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_checksum(path: Path) -> Path:
    checksum = path.with_name(path.name + ".sha256")
    checksum.write_text(f"{sha256(path)}  {path.name}\n", encoding="ascii")
    return checksum


def copy_file(root: Path, staging: Path, relative: str) -> None:
    source = root / relative
    if source.is_file():
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def run_pyinstaller(root: Path, spec_name: str) -> None:
    if os.name != "nt":
        raise SystemExit("Windows executable builds must run on Windows. Use --skip-pyinstaller only for packaging tests.")
    for name in ("build", "dist"):
        path = root / name
        if path.exists():
            shutil.rmtree(path)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec_name],
        cwd=root,
        check=True,
    )


def zip_tree(source_dir: Path, output: Path, archive_root: str) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_dir).as_posix()
            archive.write(path, f"{archive_root}/{relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/package a Windows Stories Of Yggdrasil OSC Desktop release.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Package an already-built dist tree; intended for tests only.")
    parser.add_argument("--dist-root", default=None, help="Override PyInstaller dist root when --skip-pyinstaller is used.")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    metadata = json.loads((root / "version.json").read_text(encoding="utf-8"))
    version = str(metadata["version"])
    tag = str(metadata.get("tag") or f"v{version}")
    release_notes = str(metadata.get("release_notes") or f"PATCH_NOTES_v{version}.md")
    product = str(metadata.get("product") or "Stories Of Yggdrasil OSC")
    spec_name = str(metadata.get("pyinstaller_spec") or "Stories Of Yggdrasil OSC.spec")

    if not args.skip_pyinstaller:
        run_pyinstaller(root, spec_name)

    dist_root = Path(args.dist_root).resolve() if args.dist_root else (root / "dist")
    built_app = dist_root / "Stories Of Yggdrasil OSC"
    if not built_app.is_dir():
        raise SystemExit(f"Built application folder not found: {built_app}")

    release_dir = root / "release" / tag
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)

    staging_base = root / "release" / ".staging"
    if staging_base.exists():
        shutil.rmtree(staging_base)
    staging = staging_base / product
    shutil.copytree(built_app, staging)

    for relative in (
        "README.md",
        "QUICK_START.md",
        "CHANGELOG.md",
        release_notes,
        "version.json",
    ):
        copy_file(root, staging, relative)

    contracts = root / "contracts"
    if contracts.is_dir():
        shutil.copytree(contracts, staging / "contracts")

    zip_path = release_dir / f"Stories_Of_Yggdrasil_OSC_Windows_{tag}.zip"
    zip_tree(staging, zip_path, product)
    checksum_path = write_checksum(zip_path)

    notes = root / release_notes
    if notes.is_file():
        shutil.copy2(notes, release_dir / notes.name)

    shutil.copy2(root / "version.json", release_dir / "version.json")

    manifest_entries = []
    for path in sorted(release_dir.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            manifest_entries.append(f"{sha256(path)}  {path.name}")
    (release_dir / "SHA256SUMS.txt").write_text("\n".join(manifest_entries) + "\n", encoding="ascii")

    if staging_base.exists():
        shutil.rmtree(staging_base)

    print(f"Release assets built: {release_dir}")
    for path in sorted(release_dir.iterdir()):
        if path.is_file():
            print(f" - {path.name}")
    print(f" - zip_sha256: {sha256(zip_path)}")
    print(f" - checksum_file: {checksum_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
