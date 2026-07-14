from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UpdateEvent:
    kind: str
    ok: bool
    message: str
    data: dict[str, Any]


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(x) for x in re.findall(r"\d+", str(value))[:4]]
    return tuple(parts + [0] * (4 - len(parts)))


class UpdateManager:
    """GitHub Releases updater. The UI always asks before downloading/installing."""

    def __init__(self, event_queue: queue.Queue[UpdateEvent], current_version: str) -> None:
        self.events = event_queue
        self.current_version = current_version
        self._busy = False

    def check(self, repo: str, asset_pattern: str = "") -> None:
        if self._busy:
            return
        self._busy = True
        threading.Thread(
            target=self._check_worker,
            args=(str(repo).strip(), str(asset_pattern).strip()),
            daemon=True,
            name="StoriesUpdateCheck",
        ).start()

    def download_and_install(self, release: dict[str, Any]) -> None:
        if self._busy:
            return
        self._busy = True
        threading.Thread(
            target=self._install_worker,
            args=(dict(release),),
            daemon=True,
            name="StoriesUpdateInstall",
        ).start()

    def _emit(self, kind: str, ok: bool, message: str, data: dict[str, Any] | None = None) -> None:
        self.events.put(UpdateEvent(kind, ok, message, data or {}))

    def _check_worker(self, repo: str, asset_pattern: str) -> None:
        try:
            if not repo or "/" not in repo:
                raise RuntimeError("GitHub repository is not configured. Enter owner/repository in Settings.")
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "StoriesOfYggdrasilOSC"})
            with urllib.request.urlopen(req, timeout=10) as response:
                release = json.loads(response.read().decode("utf-8", errors="replace"))
            latest = str(release.get("tag_name") or release.get("name") or "").lstrip("vV")
            assets = release.get("assets") if isinstance(release.get("assets"), list) else []
            chosen = None
            for item in assets:
                name = str(item.get("name") or "")
                if not name.lower().endswith(".zip"):
                    continue
                if asset_pattern and asset_pattern.lower() not in name.lower():
                    continue
                chosen = item
                break
            if chosen is None:
                for item in assets:
                    if str(item.get("name") or "").lower().endswith(".zip"):
                        chosen = item
                        break
            checksum_asset = None
            if chosen is not None:
                chosen_name = str(chosen.get("name") or "")
                checksum_names = {chosen_name + ".sha256", re.sub(r"\.zip$", ".sha256", chosen_name, flags=re.I)}
                checksum_asset = next((item for item in assets if str(item.get("name") or "") in checksum_names), None)
            payload = {
                "available": bool(latest and _version_tuple(latest) > _version_tuple(self.current_version)),
                "current_version": self.current_version,
                "latest_version": latest or self.current_version,
                "release_name": str(release.get("name") or release.get("tag_name") or latest),
                "release_notes": str(release.get("body") or ""),
                "published_at": release.get("published_at"),
                "asset_name": str((chosen or {}).get("name") or ""),
                "asset_url": str((chosen or {}).get("browser_download_url") or ""),
                "checksum_url": str((checksum_asset or {}).get("browser_download_url") or ""),
                "html_url": str(release.get("html_url") or ""),
            }
            if payload["available"]:
                self._emit("update_available", True, f"Version {payload['latest_version']} is available.", payload)
            else:
                self._emit("update_current", True, "You are running the latest version.", payload)
        except Exception as exc:
            self._emit("update_error", False, str(exc), {})
        finally:
            self._busy = False

    def _install_worker(self, release: dict[str, Any]) -> None:
        try:
            asset_url = str(release.get("asset_url") or "")
            asset_name = str(release.get("asset_name") or "Stories_OSC_Update.zip")
            if not asset_url:
                raise RuntimeError("The GitHub release has no downloadable ZIP asset.")
            temp_dir = Path(tempfile.mkdtemp(prefix="stories_osc_update_"))
            archive = temp_dir / asset_name
            req = urllib.request.Request(asset_url, headers={"User-Agent": "StoriesOfYggdrasilOSC"})
            with urllib.request.urlopen(req, timeout=60) as response, archive.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            if not zipfile.is_zipfile(archive):
                raise RuntimeError("Downloaded update is not a valid ZIP archive.")

            checksum_url = str(release.get("checksum_url") or "")
            if checksum_url:
                checksum_req = urllib.request.Request(checksum_url, headers={"User-Agent": "StoriesOfYggdrasilOSC"})
                with urllib.request.urlopen(checksum_req, timeout=20) as response:
                    checksum_text = response.read().decode("utf-8", errors="replace")
                match = re.search(r"\b([a-fA-F0-9]{64})\b", checksum_text)
                if not match:
                    raise RuntimeError("The release checksum file is invalid.")
                expected = match.group(1).lower()
                actual = hashlib.sha256(archive.read_bytes()).hexdigest().lower()
                if actual != expected:
                    raise RuntimeError("The downloaded update failed checksum verification.")

            install_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
            launcher = install_dir / "Start Stories OSC.bat"
            ps1 = temp_dir / "install_update.ps1"
            script = f'''$ErrorActionPreference = "Stop"
$pidToWait = {os.getpid()}
$archive = "{str(archive).replace('"','`"')}"
$install = "{str(install_dir).replace('"','`"')}"
$staging = Join-Path $env:TEMP "StoriesOSC_Staging_{os.getpid()}"
while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 300 }}
if (Test-Path $staging) {{ Remove-Item $staging -Recurse -Force }}
New-Item -ItemType Directory -Path $staging | Out-Null
Expand-Archive -Path $archive -DestinationPath $staging -Force
$source = Get-ChildItem $staging | Select-Object -First 1
if ($source.PSIsContainer -and (Get-ChildItem $staging).Count -eq 1) {{ $sourcePath = $source.FullName }} else {{ $sourcePath = $staging }}
Copy-Item (Join-Path $sourcePath '*') $install -Recurse -Force
Start-Sleep -Milliseconds 300
$launcher = Join-Path $install "Start Stories OSC.bat"
$executable = Join-Path $install "Stories Of Yggdrasil OSC.exe"
if (Test-Path $launcher) {{ Start-Process $launcher }}
elseif (Test-Path $executable) {{ Start-Process $executable }}
Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
'''
            ps1.write_text(script, encoding="utf-8")
            self._emit("update_ready", True, "Update downloaded. The program will close and install it.", {"script": str(ps1)})
        except Exception as exc:
            self._emit("update_error", False, str(exc), {})
        finally:
            self._busy = False

    @staticmethod
    def launch_installer(script_path: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Automatic installation is currently supported on Windows only.")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
