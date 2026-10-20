"""Privacy-first, local-by-default diagnostics for Desktop and installer.

No crash report ever contains an exception message, username, ID, network address,
token, raw log line, arbitrary path, or arbitrary server response. An explicitly
reviewed report can be sent only to the configured first-party HTTPS receiver.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import get_app_data_dir

KINDS = frozenset({"desktop_exception", "desktop_thread_exception", "desktop_hang",
                   "desktop_termination", "installer_error", "installer_hang"})
PHASES = frozenset({"startup", "running", "waiting_for_exit", "extract",
                    "copy", "verify", "restart", "complete", "unknown"})
RECEIVER_HOST = "admin.storiesofyggdrasil.com"
RECEIVER_PATH = "/api/osc/crash-report"
REPORT_LIMIT = 20
REPORT_ROOT = "crash_reports"


def _safe_version(value: Any) -> str:
    v = str(value or "")[:50]
    return v if re.fullmatch(r"[a-zA-Z0-9._-]{1,50}", v) else "unknown"


def _safe_symbol(value: Any) -> str:
    v = str(value or "")[:64]
    return v if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", v) else "unknown"


def _stack(exc_tb: Any) -> list[str]:
    frames: list[str] = []
    for frame in traceback.extract_tb(exc_tb)[-12:]:
        path = Path(frame.filename).as_posix().lower()
        basename = Path(frame.filename).name.lower()
        # File basenames alone can be personal; only known internal source
        # locations are allowed. Everything outside the app is "external".
        trusted_files = {"app.py", "app_v0814.py", "config.py", "controller.py",
                         "update_manager.py", "crash_reporting.py", "sam_client.py",
                         "osc_service.py", "combat.py", "combat_authority.py",
                         "avatar_compatibility.py", "qol.py", "models.py",
                         "telemetry.py", "tls_runtime.py", "winhttp_transport.py",
                         "helpful_items.py", "vrchat_config.py"}
        trusted = "/stories_yggdrasil_osc/" in path.replace("\\", "/") and basename in trusted_files
        module = basename if trusted else "external"
        function = _safe_symbol(frame.name) if trusted else "unknown"
        frames.append(module + ":" + function)
    return frames


def _report_dir() -> Path:
    root = get_app_data_dir() / REPORT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_report(kind: str, version: str, *, phase: str = "unknown",
                exception: BaseException | None = None) -> dict[str, Any]:
    """Allowlisted schema only: no diagnostic message strings are accepted."""
    result: dict[str, Any] = {
        "schema": 1,
        "report_id": uuid.uuid4().hex,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product": "Stories Of Yggdrasil OSC",
        "version": _safe_version(version),
        "os": "Windows" if sys.platform == "win32" else "Other",
        "kind": kind if kind in KINDS else "desktop_exception",
        "phase": phase if phase in PHASES else "unknown",
    }
    if exception is not None:
        result["exception_type"] = _safe_symbol(type(exception).__name__)
        result["stack"] = _stack(exception.__traceback__)
    return result


def save_report(report: dict[str, Any]) -> Path:
    """Drop any unknown or attacker-supplied fields before storing or sending."""
    allowed = ("schema", "report_id", "created_utc", "product", "version", "os",
               "kind", "phase", "exception_type", "stack")
    clean = {key: report[key] for key in allowed if key in report}
    if clean.get("schema") != 1 or clean.get("product") != "Stories Of Yggdrasil OSC":
        raise ValueError("Invalid crash-report schema")
    clean["kind"] = clean.get("kind") if clean.get("kind") in KINDS else "desktop_exception"
    clean["phase"] = clean.get("phase") if clean.get("phase") in PHASES else "unknown"
    clean["version"] = _safe_version(clean.get("version"))
    clean["exception_type"] = _safe_symbol(clean["exception_type"]) if "exception_type" in clean else None
    clean["stack"] = [x for x in clean.get("stack", []) if isinstance(x, str) and
                      re.fullmatch(r"(?:app(?:_v0814)?\.py|config\.py|controller\.py|update_manager\.py|crash_reporting\.py|sam_client\.py|osc_service\.py|combat\.py|combat_authority\.py|avatar_compatibility\.py|qol\.py|models\.py|telemetry\.py|tls_runtime\.py|winhttp_transport\.py|helpful_items\.py|vrchat_config\.py):[A-Za-z_][A-Za-z0-9_]{0,63}|external:unknown", x)][:12]
    clean["os"] = "Windows" if clean.get("os") == "Windows" else "Other"
    clean["report_id"] = str(clean.get("report_id") or "")[:32]
    if not re.fullmatch(r"[0-9a-f]{32}", clean["report_id"]):
        raise ValueError("Invalid report ID")
    # The timestamp is generated internally; validate before sharing.
    stamp = str(clean.get("created_utc") or "")[:32]
    try:
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid report timestamp") from exc
    clean["created_utc"] = stamp
    clean.pop("exception_type", None) if clean.get("exception_type") is None else None
    if not clean["stack"]:
        clean.pop("stack", None)
    folder = _report_dir()
    dest = folder / ("pending_" + clean["report_id"] + ".json")
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    os.replace(temp, dest)
    files = sorted(folder.glob("pending_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[REPORT_LIMIT:]:
        old.unlink(missing_ok=True)
    return dest


def pending_reports() -> list[Path]:
    return sorted(_report_dir().glob("pending_*.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True)[:REPORT_LIMIT]


def load_report(path: Path) -> dict[str, Any]:
    if not path.name.startswith("pending_") or path.parent.resolve() != _report_dir().resolve():
        raise ValueError("Crash report outside the pending folder")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Invalid report")
    # Rebuild only approved, strictly typed fields on read as well.
    if result.get("schema") != 1 or result.get("product") != "Stories Of Yggdrasil OSC":
        raise ValueError("Invalid report")
    safe = {k: result[k] for k in ("schema", "report_id", "created_utc", "product",
           "version", "os", "kind", "phase", "exception_type", "stack") if k in result}
    safe["version"] = _safe_version(safe.get("version"))
    safe["kind"] = safe["kind"] if safe.get("kind") in KINDS else "desktop_exception"
    safe["phase"] = safe["phase"] if safe.get("phase") in PHASES else "unknown"
    safe["os"] = "Windows" if safe.get("os") == "Windows" else "Other"
    safe["exception_type"] = _safe_symbol(safe["exception_type"]) if "exception_type" in safe else None
    safe["stack"] = [x for x in safe.get("stack", []) if isinstance(x, str) and
                     re.fullmatch(r"(?:app(?:_v0814)?\.py|config\.py|controller\.py|update_manager\.py|crash_reporting\.py|sam_client\.py|osc_service\.py|combat\.py|combat_authority\.py|avatar_compatibility\.py|qol\.py|models\.py|telemetry\.py|tls_runtime\.py|winhttp_transport\.py|helpful_items\.py|vrchat_config\.py):[A-Za-z_][A-Za-z0-9_]{0,63}|external:unknown", x)][:12]
    if not re.fullmatch(r"[0-9a-f]{32}", str(safe.get("report_id", ""))):
        raise ValueError("Invalid report ID")
    try:
        timestamp = datetime.fromisoformat(str(safe.get("created_utc", "")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Report timestamp missing timezone")
        safe["created_utc"] = timestamp.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid report timestamp") from exc
    if safe.get("exception_type") is None:
        safe.pop("exception_type", None)
    if not safe["stack"]:
        safe.pop("stack", None)
    return safe


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def send_report(path: Path, endpoint: str, *, consent: bool) -> None:
    """Explicit action only. Never use Sam.py pairing/authentication credentials."""
    if not consent:
        raise PermissionError("Crash reporting is disabled in Privacy settings")
    url = urlsplit(str(endpoint))
    if (url.scheme != "https" or url.hostname != RECEIVER_HOST or
            url.port not in (None, 443) or url.path != RECEIVER_PATH or
            url.query or url.fragment or url.username or url.password):
        raise ValueError("A verified first-party HTTPS crash receiver is not configured")
    data = json.dumps(load_report(path), separators=(",", ":")).encode("utf-8")
    if len(data) > 8192:
        raise ValueError("Report exceeds size limit")
    req = urllib.request.Request(endpoint, data=data,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "StoriesOSC-CrashReporter"},
                                 method="POST")
    from .tls_runtime import get_ssl_context
    opener = urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=get_ssl_context()))
    with opener.open(req, timeout=8) as response:
        if response.status not in (200, 201, 202, 204):
            raise RuntimeError("Crash receiver did not accept the report")
    path.unlink(missing_ok=True)


def record_exception(exc: BaseException, version: str, *, thread: bool = False) -> None:
    try:
        save_report(make_report("desktop_thread_exception" if thread else "desktop_exception",
                                version, phase="running", exception=exc))
    except Exception:
        pass


def _is_process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        k32.WaitForSingleObject.restype = ctypes.c_ulong
        k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = k32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            return k32.WaitForSingleObject(handle, 0) == 0x102
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def watchdog_main(pid: int, session: str, version: str) -> int:
    folder = _report_dir()
    marker = folder / ("heartbeat_" + session + ".json")
    clean = folder / ("clean_" + session)
    stalled = False
    started = time.monotonic()
    while time.monotonic() - started < 86400:
        if clean.exists():
            return 0
        if not _is_process_alive(pid):
            if not stalled and not clean.exists():
                save_report(make_report("desktop_termination", version, phase="running"))
            return 0
        try:
            last = marker.stat().st_mtime
        except OSError:
            last = time.time() if time.monotonic() - started < 20 else 0
        if time.time() - last > 25 and not stalled:
            stalled = True
            save_report(make_report("desktop_hang", version, phase="running"))
        if time.time() - last < 6:
            stalled = False
        time.sleep(2)
    return 0


def start_runtime_monitor(root: Any, version: str) -> Any:
    """Main-thread heartbeat; independent child detects a genuinely wedged Tk loop."""
    folder = _report_dir()
    session = uuid.uuid4().hex
    marker = folder / ("heartbeat_" + session + ".json")
    clean = folder / ("clean_" + session)
    closed = False

    def heartbeat() -> None:
        if closed:
            return
        try:
            marker.touch()
        except OSError:
            pass
        root.after(1500, heartbeat)

    # A frozen PyInstaller binary relaunches itself; source runs use main.py.
    command = ([sys.executable, "--soy-watchdog", str(os.getpid()), session, version]
               if getattr(sys, "frozen", False)
               else [sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"),
                     "--soy-watchdog", str(os.getpid()), session, version])
    try:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        pass
    heartbeat()

    class Monitor:
        def close(self) -> None:
            nonlocal closed
            closed = True
            try:
                clean.touch()
                marker.unlink(missing_ok=True)
            except OSError:
                pass

    return Monitor()
