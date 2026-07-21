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
    """GitHub Releases updater with visible download/install progress."""

    def __init__(self, event_queue: queue.Queue[UpdateEvent], current_version: str) -> None:
        self.events = event_queue
        self.current_version = current_version
        self._busy = False
        self._lock = threading.RLock()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def _set_busy(self, value: bool) -> bool:
        with self._lock:
            if value and self._busy:
                return False
            self._busy = value
            return True

    def check(self, repo: str, asset_pattern: str = "") -> None:
        if not self._set_busy(True):
            return
        threading.Thread(
            target=self._check_worker,
            args=(str(repo).strip(), str(asset_pattern).strip()),
            daemon=True,
            name="StoriesUpdateCheck",
        ).start()

    def download_and_install(self, release: dict[str, Any]) -> None:
        if not self._set_busy(True):
            return
        threading.Thread(
            target=self._install_worker,
            args=(dict(release),),
            daemon=True,
            name="StoriesUpdateInstall",
        ).start()

    def _emit(self, kind: str, ok: bool, message: str, data: dict[str, Any] | None = None) -> None:
        self.events.put(UpdateEvent(kind, ok, message, data or {}))

    def _progress(self, percent: float, message: str, phase: str) -> None:
        self._emit(
            "update_progress",
            True,
            message,
            {
                "percent": max(0.0, min(100.0, float(percent))),
                "phase": str(phase),
            },
        )

    def _check_worker(self, repo: str, asset_pattern: str) -> None:
        try:
            self._progress(5, "Checking GitHub for updates…", "check")
            if not repo or "/" not in repo:
                raise RuntimeError("GitHub repository is not configured. Enter owner/repository in Settings.")
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "StoriesOfYggdrasilOSC",
                },
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                release = json.loads(response.read().decode("utf-8", errors="replace"))
            self._progress(70, "Reading the latest release…", "check")
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
                checksum_names = {
                    chosen_name + ".sha256",
                    re.sub(r"\.zip$", ".sha256", chosen_name, flags=re.I),
                }
                checksum_asset = next(
                    (item for item in assets if str(item.get("name") or "") in checksum_names),
                    None,
                )
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
            self._progress(100, "Update check complete.", "check")
            if payload["available"]:
                self._emit("update_available", True, f"Version {payload['latest_version']} is available.", payload)
            else:
                self._emit("update_current", True, "You are running the latest version.", payload)
        except Exception as exc:
            self._emit("update_error", False, str(exc), {})
        finally:
            self._set_busy(False)

    def _install_worker(self, release: dict[str, Any]) -> None:
        try:
            asset_url = str(release.get("asset_url") or "")
            asset_name = str(release.get("asset_name") or "Stories_OSC_Update.zip")
            expected_version = str(release.get("latest_version") or "").strip()
            if not asset_url:
                raise RuntimeError("The GitHub release has no downloadable Windows ZIP asset.")

            temp_dir = Path(tempfile.mkdtemp(prefix="stories_osc_update_"))
            archive = temp_dir / asset_name
            self._progress(1, "Connecting to the release download…", "download")
            req = urllib.request.Request(asset_url, headers={"User-Agent": "StoriesOfYggdrasilOSC"})
            with urllib.request.urlopen(req, timeout=90) as response, archive.open("wb") as handle:
                try:
                    total = int(response.headers.get("Content-Length") or 0)
                except Exception:
                    total = 0
                received = 0
                last_percent = -1
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    handle.write(chunk)
                    received += len(chunk)
                    if total > 0:
                        fraction = min(1.0, received / total)
                        percent = int(5 + fraction * 70)
                    else:
                        percent = min(75, 5 + int(received / (1024 * 1024)))
                    if percent != last_percent:
                        last_percent = percent
                        size_text = f"{received / (1024 * 1024):.1f} MB"
                        self._progress(percent, f"Downloading update… {size_text}", "download")

            if not zipfile.is_zipfile(archive):
                raise RuntimeError("Downloaded update is not a valid ZIP archive.")

            self._progress(79, "Verifying the downloaded update…", "verify")
            checksum_url = str(release.get("checksum_url") or "")
            if checksum_url:
                checksum_req = urllib.request.Request(checksum_url, headers={"User-Agent": "StoriesOfYggdrasilOSC"})
                with urllib.request.urlopen(checksum_req, timeout=25) as response:
                    checksum_text = response.read().decode("utf-8", errors="replace")
                match = re.search(r"\b([a-fA-F0-9]{64})\b", checksum_text)
                if not match:
                    raise RuntimeError("The release checksum file is invalid.")
                expected = match.group(1).lower()
                actual = hashlib.sha256(archive.read_bytes()).hexdigest().lower()
                if actual != expected:
                    raise RuntimeError("The downloaded update failed checksum verification.")

            self._progress(88, "Preparing the updater…", "prepare")
            install_dir = (
                Path(sys.executable).resolve().parent
                if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parents[1]
            )
            app_data = Path(os.getenv("APPDATA", tempfile.gettempdir())) / "StoriesOfYggdrasil" / "OSCContactSystem"
            app_data.mkdir(parents=True, exist_ok=True)
            log_path = app_data / "update_install.log"
            result_path = app_data / "update_result.json"
            ps1 = temp_dir / "install_update.ps1"

            def ps_quote(value: Path | str) -> str:
                return str(value).replace("'", "''")

            script = r'''$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$pidToWait = __PID__
$archive = '__ARCHIVE__'
$install = '__INSTALL__'
$expectedVersion = '__VERSION__'
$logPath = '__LOG__'
$resultPath = '__RESULT__'
$staging = Join-Path $env:TEMP "StoriesOSC_Staging___PID__"

$form = New-Object System.Windows.Forms.Form
$form.Text = "Stories Of Yggdrasil OSC Update"
$form.Size = New-Object System.Drawing.Size(520,155)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(20,18)
$label.Size = New-Object System.Drawing.Size(470,28)
$label.Text = "Waiting for Stories Of Yggdrasil OSC to close…"
$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(20,58)
$bar.Size = New-Object System.Drawing.Size(470,26)
$bar.Minimum = 0
$bar.Maximum = 100
$bar.Value = 5
$form.Controls.Add($label)
$form.Controls.Add($bar)
$form.Show()
[System.Windows.Forms.Application]::DoEvents()

function Set-UpdateProgress([int]$value, [string]$text) {
    $bar.Value = [Math]::Max(0, [Math]::Min(100, $value))
    $label.Text = $text
    $form.Refresh()
    [System.Windows.Forms.Application]::DoEvents()
}

function Write-UpdateLog([string]$text) {
    $line = "$(Get-Date -Format o) $text"
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}

try {
    New-Item -ItemType Directory -Force -Path (Split-Path $logPath -Parent) | Out-Null
    Write-UpdateLog "Installer started. Target=$install Expected=$expectedVersion"
    $waitCount = 0
    while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 250
        $waitCount++
        if ($waitCount -gt 240) { throw "Timed out waiting for the application to close." }
    }

    Set-UpdateProgress 20 "Extracting the update…"
    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
    New-Item -ItemType Directory -Path $staging | Out-Null
    Expand-Archive -Path $archive -DestinationPath $staging -Force
    $children = @(Get-ChildItem $staging)
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) { $sourcePath = $children[0].FullName }
    else { $sourcePath = $staging }
    $sourceExe = Join-Path $sourcePath "Stories Of Yggdrasil OSC.exe"
    if (!(Test-Path $sourceExe)) { throw "The release archive does not contain Stories Of Yggdrasil OSC.exe." }

    Set-UpdateProgress 50 "Installing the new version…"
    New-Item -ItemType Directory -Force -Path $install | Out-Null
    & robocopy $sourcePath $install /E /COPY:DAT /DCOPY:DAT /R:5 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    $copyCode = $LASTEXITCODE
    if ($copyCode -gt 7) { throw "File installation failed with Robocopy code $copyCode." }

    Set-UpdateProgress 82 "Verifying the installed files…"
    $installedExe = Join-Path $install "Stories Of Yggdrasil OSC.exe"
    if (!(Test-Path $installedExe)) { throw "The updated executable was not installed." }
    $installedVersionFile = Join-Path $install "version.json"
    $installedVersion = ""
    if (Test-Path $installedVersionFile) {
        try { $installedVersion = (Get-Content $installedVersionFile -Raw | ConvertFrom-Json).version } catch { }
    }
    if ($expectedVersion -and $installedVersion -and $installedVersion -ne $expectedVersion) {
        throw "Installed version $installedVersion does not match expected version $expectedVersion."
    }

    @{ ok = $true; version = $installedVersion; installed_at = (Get-Date).ToString("o") } |
        ConvertTo-Json | Set-Content -Path $resultPath -Encoding UTF8
    Write-UpdateLog "Install succeeded. InstalledVersion=$installedVersion"
    Set-UpdateProgress 100 "Update complete. Restarting…"
    Start-Sleep -Milliseconds 650
    Start-Process $installedExe
    Start-Sleep -Milliseconds 450
    $form.Close()
}
catch {
    $message = $_.Exception.Message
    Write-UpdateLog "Install failed: $message"
    @{ ok = $false; error = $message; failed_at = (Get-Date).ToString("o") } |
        ConvertTo-Json | Set-Content -Path $resultPath -Encoding UTF8
    Set-UpdateProgress 100 "Update failed."
    [System.Windows.Forms.MessageBox]::Show(
        "The update could not be installed.`n`n$message`n`nLog: $logPath",
        "Stories OSC Update Failed",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    $oldExe = Join-Path $install "Stories Of Yggdrasil OSC.exe"
    if (Test-Path $oldExe) { Start-Process $oldExe }
    $form.Close()
}
finally {
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
}
'''
            script = (
                script.replace("__PID__", str(os.getpid()))
                .replace("__ARCHIVE__", ps_quote(archive))
                .replace("__INSTALL__", ps_quote(install_dir))
                .replace("__VERSION__", expected_version.replace("'", "''"))
                .replace("__LOG__", ps_quote(log_path))
                .replace("__RESULT__", ps_quote(result_path))
            )
            ps1.write_text(script, encoding="utf-8-sig")
            self._progress(100, "Update downloaded and ready to install.", "ready")
            self._emit(
                "update_ready",
                True,
                "Update downloaded. The installer will show its own progress while files are replaced.",
                {
                    "script": str(ps1),
                    "version": expected_version,
                    "log_path": str(log_path),
                },
            )
        except Exception as exc:
            self._emit("update_error", False, str(exc), {})
        finally:
            self._set_busy(False)

    @staticmethod
    def launch_installer(script_path: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Automatic installation is currently supported on Windows only.")
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                script_path,
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
