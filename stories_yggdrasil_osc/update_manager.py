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

from .tls_runtime import get_ssl_context


@dataclass(frozen=True)
class UpdateEvent:
    kind: str
    ok: bool
    message: str
    data: dict[str, Any]


def _version_tuple(value: str) -> tuple[int, ...]:
    """Order stable releases after their matching pre-builds.

    Examples:
      0.8.21-prebuild.4 < 0.8.21 < 0.8.22-prebuild.1
    """
    text = str(value or "").strip().lstrip("vV")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-prebuild\.(\d+))?", text, flags=re.I)
    if match:
        major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
        prebuild = match.group(4)
        return (major, minor, patch, 0 if prebuild is not None else 1, int(prebuild or 0))
    parts = [int(x) for x in re.findall(r"\d+", text)[:4]]
    return tuple(parts + [0] * (5 - len(parts)))


def _release_version(release: dict[str, Any]) -> str:
    return str(release.get("tag_name") or release.get("name") or "").lstrip("vV")


def _select_release(releases: list[dict[str, Any]], channel: str) -> dict[str, Any] | None:
    normalized = str(channel or "stable").strip().lower()
    allow_test = normalized in {"test", "test-builds", "test builds", "pre-build", "prebuild"}
    eligible = [
        release for release in releases
        if isinstance(release, dict)
        and not bool(release.get("draft"))
        and (allow_test or not bool(release.get("prerelease")))
        and _release_version(release)
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda release: _version_tuple(_release_version(release)))


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

    def check(self, repo: str, asset_pattern: str = "", channel: str = "stable") -> None:
        if not self._set_busy(True):
            return
        threading.Thread(
            target=self._check_worker,
            args=(str(repo).strip(), str(asset_pattern).strip(), str(channel or "stable").strip()),
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

    def _check_worker(self, repo: str, asset_pattern: str, channel: str) -> None:
        try:
            normalized_channel = str(channel or "stable").strip().lower()
            use_test_channel = normalized_channel in {"test", "test-builds", "test builds", "pre-build", "prebuild"}
            channel_label = "Test Builds" if use_test_channel else "Stable"
            self._progress(5, f"Checking GitHub {channel_label} channel for updates…", "check")
            if not repo or "/" not in repo:
                raise RuntimeError("GitHub repository is not configured. Enter owner/repository in Settings.")

            if use_test_channel:
                url = f"https://api.github.com/repos/{repo}/releases?per_page=30"
            else:
                url = f"https://api.github.com/repos/{repo}/releases/latest"

            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "StoriesOfYggdrasilOSC",
                },
            )
            with urllib.request.urlopen(req, timeout=12, context=get_ssl_context()) as response:
                raw = json.loads(response.read().decode("utf-8", errors="replace"))

            if use_test_channel:
                releases = raw if isinstance(raw, list) else []
                release = _select_release(releases, "test")
                if release is None:
                    raise RuntimeError("No Stable or Test Build GitHub release is available.")
            else:
                if not isinstance(raw, dict):
                    raise RuntimeError("GitHub returned an invalid Stable release response.")
                release = raw

            self._progress(70, f"Reading the latest {channel_label} release…", "check")
            latest = _release_version(release)
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
                "prerelease": bool(release.get("prerelease")),
                "channel": "test" if use_test_channel else "stable",
                "channel_label": channel_label,
                "asset_name": str((chosen or {}).get("name") or ""),
                "asset_url": str((chosen or {}).get("browser_download_url") or ""),
                "checksum_url": str((checksum_asset or {}).get("browser_download_url") or ""),
                "html_url": str(release.get("html_url") or ""),
            }
            self._progress(100, "Update check complete.", "check")
            if payload["available"]:
                self._emit("update_available", True, f"Version {payload['latest_version']} is available on {channel_label}.", payload)
            else:
                self._emit("update_current", True, f"You are running the latest version for {channel_label}.", payload)
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
            with urllib.request.urlopen(req, timeout=90, context=get_ssl_context()) as response, archive.open("wb") as handle:
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
                with urllib.request.urlopen(checksum_req, timeout=25, context=get_ssl_context()) as response:
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
$installerLock = [System.Threading.Mutex]::new($false, "Local\StoriesOSC_Updater")
$lockAcquired = $false

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
    try {
        $lockAcquired = $installerLock.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $lockAcquired = $true
    }
    if (-not $lockAcquired) {
        $form.Close()
        exit 3
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $logPath -Parent) | Out-Null
    Write-UpdateLog "Installer started. Target=$install Expected=$expectedVersion"
    $waitCount = 0
    while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 250
        [System.Windows.Forms.Application]::DoEvents()
        $waitCount++
        if ($waitCount -gt 240) { throw "Timed out waiting for the application to close." }
    }

    $phasePath = Join-Path (Split-Path $logPath -Parent) "update_phase.json"
    $attemptId = [guid]::NewGuid().ToString("N")
    $workerResult = Join-Path (Split-Path $logPath -Parent) ("update_worker_result_" + $attemptId + ".json")
    $workerScript = Join-Path $env:TEMP ("StoriesOSC_worker_" + $attemptId + ".ps1")
    # This must run before the worker, or an old 92% phase can be shown.
    Remove-Item -LiteralPath $phasePath, $workerResult, $resultPath -Force -ErrorAction SilentlyContinue
    $workerCode = @'
$ErrorActionPreference = "Stop"
$archive = '__ARCHIVE__'
$install = '__INSTALL__'
$expected = '__VERSION__'
$stageDir = Join-Path $env:TEMP ("StoriesOSC_Staging_" + [guid]::NewGuid().ToString("N"))
$phasePath = '__PHASEFILE__'
$outcomePath = '__OUTCOMEFILE__'
function Progress([string]$stage, [int]$percent, [int]$fileIndex = 0, [int]$fileTotal = 0, [long]$bytes = 0) {
    # A single worker owns this checkpoint file. Windows PowerShell Move-Item
    # -Force can fail with "file already exists" when the parent UI briefly
    # has the destination open for reading. Write in place instead: the UI
    # already tolerates a partially-written JSON checkpoint and retries.
    $statusJson = @{ phase = $stage; percent = $percent; file_index = $fileIndex;
       file_total = $fileTotal; bytes_extracted = $bytes;
       utc = (Get-Date).ToUniversalTime().ToString("o") } | ConvertTo-Json -Compress
    for ($attempt = 0; $attempt -lt 8; $attempt++) {
        try {
            [System.IO.File]::WriteAllText($phasePath, $statusJson, [System.Text.Encoding]::UTF8)
            return
        } catch [System.IO.IOException] {
            if ($attempt -eq 7) { throw "Could not update installer progress checkpoint after retries." }
            Start-Sleep -Milliseconds 40
        }
    }
}
try {
    Progress "extract" 20
    # Expand-Archive can block without emitting progress on Windows PowerShell.
    # Instead stream each ZIP entry via .NET, with periodic checkpoint updates.
    Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
    [System.IO.Directory]::CreateDirectory($stageDir) | Out-Null
    $root = [System.IO.Path]::GetFullPath($stageDir).TrimEnd([char]'\') + '\'
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $entries = $zip.Entries
        if ($entries.Count -gt 12000) { throw "Release contains too many files." }
        [long]$totalSize = 0
        foreach ($entry in $entries) {
            $totalSize += [long]$entry.Length
            if ($totalSize -gt 2147483648) { throw "Release exceeds unpacked size limit." }
        }
        [long]$written = 0
        [int]$count = 0
        $lastCheckpoint = [DateTime]::UtcNow
        $buffer = New-Object byte[] (1024 * 1024)
        foreach ($entry in $entries) {
            $name = $entry.FullName.Replace([char]'/', [char]'\')
            if ([string]::IsNullOrWhiteSpace($name) -or $name.Contains(':') -or $name.StartsWith('\')) {
                throw "Release contains an invalid archive path."
            }
            # ZIP links must not escape the controlled staging tree.
            $unixType = ($entry.ExternalAttributes -shr 16) -band 61440
            if ($unixType -eq 40960) { throw "Release contains an unsupported symbolic link." }
            $target = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root, $name))
            if (-not $target.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Release contains an out-of-root archive path."
            }
            $isDirectory = $name.EndsWith('\')
            if ($isDirectory) {
                [System.IO.Directory]::CreateDirectory($target) | Out-Null
            } else {
                [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target)) | Out-Null
                $inputStream = $entry.Open()
                # Staging is a fresh GUID-scoped directory. Using Create
                # permits a repeated archive entry to replace the earlier one,
                # instead of aborting installation with ERROR_FILE_EXISTS.
                # Paths and link types are already checked above.
                $outputStream = [System.IO.File]::Open($target,
                    [System.IO.FileMode]::Create,
                    [System.IO.FileAccess]::Write,
                    [System.IO.FileShare]::None)
                try {
                    while (($bytesRead = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                        $outputStream.Write($buffer, 0, $bytesRead)
                        $written += $bytesRead
                        if (([DateTime]::UtcNow - $lastCheckpoint).TotalSeconds -ge 1) {
                            $pct = 20 + [int][Math]::Floor(26 * $written / [Math]::Max(1.0, [double]$totalSize))
                            Progress "extract" ([Math]::Min(46, $pct)) ($count + 1) $entries.Count $written
                            $lastCheckpoint = [DateTime]::UtcNow
                        }
                    }
                } finally {
                    $outputStream.Dispose()
                    $inputStream.Dispose()
                }
            }
            $count += 1
            if (($count % 10 -eq 0) -or $count -eq $entries.Count) {
                $pct = 20 + [int][Math]::Floor(26 * $written / [Math]::Max(1.0, [double]$totalSize))
                Progress "extract" ([Math]::Min(46, $pct)) $count $entries.Count $written
                $lastCheckpoint = [DateTime]::UtcNow
            }
        }
    } finally {
        $zip.Dispose()
    }
    Progress "extract" 47 $count $entries.Count $written
    $children = @(Get-ChildItem -LiteralPath $stageDir)
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
        $source = $children[0].FullName
    } else {
        $source = $stageDir
    }
    if (!(Test-Path -LiteralPath (Join-Path $source "Stories Of Yggdrasil OSC.exe"))) {
        throw "Release does not contain the application executable."
    }
    Progress "copy" 50
    New-Item -ItemType Directory -Force -Path $install | Out-Null
    & robocopy $source $install /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Robocopy failed: $LASTEXITCODE" }
    Progress "verify" 82
    $exe = Join-Path $install "Stories Of Yggdrasil OSC.exe"
    $metadata = Join-Path $install "version.json"
    if (!(Test-Path -LiteralPath $exe) -or !(Test-Path -LiteralPath $metadata)) {
        throw "Updated executable or metadata missing after copy."
    }
    $actual = (Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json).version
    if ($actual -ne $expected) { throw "Installed version differs from the expected release." }
    Progress "restart" 92
    @{ ok = $true; version = $actual } |
      ConvertTo-Json | Set-Content -LiteralPath $outcomePath -Encoding UTF8
    exit 0
} catch {
    @{ ok = $false; error = $_.Exception.Message } |
      ConvertTo-Json | Set-Content -LiteralPath $outcomePath -Encoding UTF8
    exit 1
}
'@
    $workerCode = $workerCode.Replace("__PHASEFILE__", $phasePath.Replace("'", "''"))
    $workerCode = $workerCode.Replace("__OUTCOMEFILE__", $workerResult.Replace("'", "''"))
    $workerCode | Set-Content -LiteralPath $workerScript -Encoding UTF8
    # An independent process avoids the Start-Job / Receive-Job completion
    # deadlock observed with the old PowerShell installer.
    $workerArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $workerScript + '"'
    $worker = Start-Process -FilePath "powershell.exe" -ArgumentList $workerArgs -WindowStyle Hidden -PassThru
    Write-UpdateLog "Worker started. Pid=$($worker.Id)"
    $phaseName = "extract"
    $lastPhase = ""
    $lastCheckpointUtc = ""
    $phaseSince = Get-Date
    $totalSince = Get-Date
    $fileIndex = 0
    $fileTotal = 0
    $phaseLabels = @{ extract = "Extracting update"; copy = "Copying updated files"; verify = "Verifying installation"; restart = "Preparing restart" }
    while ($true) {
        $worker.Refresh()
        if (Test-Path -LiteralPath $phasePath) {
            try {
                $status = Get-Content -LiteralPath $phasePath -Raw | ConvertFrom-Json
                if ($status.phase -in @("extract","copy","verify","restart")) {
                    if ($status.phase -ne $lastPhase) {
                        $lastPhase = $status.phase
                        $phaseName = $lastPhase
                        Write-UpdateLog "Installer phase: $phaseName"
                    }
                    # Each atomic checkpoint proves forward progress, even if
                    # the extraction phase itself has not changed.
                    if ([string]$status.utc -ne $lastCheckpointUtc) {
                        $lastCheckpointUtc = [string]$status.utc
                        $phaseSince = Get-Date
                    }
                    $fileIndex = [int]$status.file_index
                    $fileTotal = [int]$status.file_total
                    $labelText = "$($phaseLabels[$phaseName])…"
                    if ($phaseName -eq "extract" -and $fileTotal -gt 0) {
                        $labelText = "Extracting update… file $fileIndex of $fileTotal"
                    }
                    Set-UpdateProgress ([int]$status.percent) $labelText
                }
            } catch { }
        }
        if ($worker.HasExited) { break }
        if (((Get-Date) - $phaseSince).TotalSeconds -ge 180 -or
            ((Get-Date) - $totalSince).TotalSeconds -ge 900) {
            try { $worker.Kill() } catch {}
            Write-UpdateLog "Worker timeout. Phase=$phaseName File=$fileIndex/$fileTotal"
            throw "Update worker stalled in phase $phaseName (file $fileIndex of $fileTotal)."
        }
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 150
    }
    if (!(Test-Path -LiteralPath $workerResult)) {
        throw "Installer worker exited without status; exit code $($worker.ExitCode)."
    }
    $outcome = Get-Content -LiteralPath $workerResult -Raw | ConvertFrom-Json
    if ($worker.ExitCode -ne 0 -or !$outcome.ok) {
        throw "Installer worker failed during $phaseName. $($outcome.error)"
    }
    $installedExe = Join-Path $install "Stories Of Yggdrasil OSC.exe"
    $metadata = Join-Path $install "version.json"
    if (!(Test-Path -LiteralPath $installedExe) -or !(Test-Path -LiteralPath $metadata)) {
        throw "Installed application or version metadata is missing."
    }
    $installedVersion = (Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json).version
    if ($installedVersion -ne $expectedVersion -or $installedVersion -ne $outcome.version) {
        throw "Parent verification failed: installed version mismatch."
    }
    Write-UpdateLog "Verified new install. InstalledVersion=$installedVersion"

    Set-UpdateProgress 96 "Launching updated application…"
    $launched = Start-Process -FilePath $installedExe -WorkingDirectory $install -PassThru
    Start-Sleep -Milliseconds 900
    $launched.Refresh()
    if ($launched.HasExited) { throw "Updated application exited immediately after restart." }
    @{ ok = $true; version = $installedVersion; installed_at = (Get-Date).ToString("o") } |
        ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-UpdateLog "Install succeeded. InstalledVersion=$installedVersion RestartPid=$($launched.Id)"
    Set-UpdateProgress 100 "Update complete."
    $form.Close()
}
catch {
    $message = $_.Exception.Message
    Write-UpdateLog "Install failed: $message"
    $safePhase = if ($phaseName -in @("extract","copy","verify","restart")) { $phaseName } else { "unknown" }
    @{ ok = $false; error = $message; phase = $safePhase; version = $expectedVersion; failed_at = (Get-Date).ToString("o") } |
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
    # Never block the UI deleting a potentially large staging tree.
    if ($lockAcquired) { try { $installerLock.ReleaseMutex() } catch {} }
    if ($installerLock) { $installerLock.Dispose() }
    if (!$form.IsDisposed) { $form.Close() }
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
