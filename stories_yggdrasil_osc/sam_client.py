from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SamEvent:
    kind: str
    ok: bool
    message: str
    data: dict[str, Any]
    source: str = ""


class SamClient:
    """Small background HTTP client for Sam.py's restricted OSC API."""

    def __init__(self, event_queue: queue.Queue[SamEvent], config: dict[str, Any]) -> None:
        self.event_queue = event_queue
        self._commands: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._config = dict(config)
        self._next_poll_at = 0.0

    def reconfigure(self, config: dict[str, Any]) -> None:
        with self._lock:
            self._config = dict(config)
            self._next_poll_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="StoriesSamBridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._commands.put_nowait(("stop", {}))
        except Exception:
            pass

    def pair(self, code: str, device_name: str) -> None:
        self._commands.put(("pair", {"code": code, "device_name": device_name}))

    def test(self) -> None:
        self._commands.put(("test", {}))

    def pull(self) -> None:
        self._commands.put(("pull", {}))

    def sync(self, payload: dict[str, Any]) -> None:
        self._commands.put(("sync", payload))

    def unlink(self) -> None:
        self._commands.put(("unlink", {}))

    def recovery_options(self) -> None:
        self._commands.put(("recovery_options", {}))

    def use_recovery(self, kind: str, name: str) -> None:
        self._commands.put(("use_recovery", {"kind": str(kind), "name": str(name)}))

    def _snapshot_config(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._config)

    @staticmethod
    def _base_url(config: dict[str, Any]) -> str:
        return str(config.get("base_url") or "https://admin.storiesofyggdrasil.com/api/osc").strip().rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        use_auth: bool = False,
        timeout: float = 6.0,
    ) -> dict[str, Any]:
        config = self._snapshot_config()
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if use_auth:
            token = str(config.get("token") or "").strip()
            if not token:
                raise RuntimeError("This device is not paired with Sam.py.")
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            self._base_url(config) + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                result = json.loads(raw) if raw else {}
                if not isinstance(result, dict):
                    raise RuntimeError("Sam.py returned an invalid response.")
                return result
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("detail")
            except Exception:
                detail = raw or str(exc)
            raise RuntimeError(f"Sam.py HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Sam.py: {exc.reason}") from exc

    def _emit(self, kind: str, ok: bool, message: str, data: dict[str, Any] | None = None, *, source: str = "") -> None:
        self.event_queue.put(SamEvent(kind, ok, message, data or {}, source))

    def _do_command(self, command: str, payload: dict[str, Any]) -> None:
        if command == "pair":
            result = self._request("POST", "/pair", payload=payload)
            self._emit("paired", True, "Device paired with Sam.py.", result, source="pair")
        elif command == "test":
            health = self._request("GET", "/health")
            token = str(self._snapshot_config().get("token") or "").strip()
            if token:
                state = self._request("GET", "/state", use_auth=True)
                health["state_response"] = state
            self._emit("test", True, "Sam.py connection test passed.", health, source="test")
        elif command == "pull":
            result = self._request("GET", "/state", use_auth=True)
            self._emit("state", True, "Pulled active character state from Sam.py.", result, source="pull")
        elif command == "sync":
            result = self._request("POST", "/sync", payload=payload, use_auth=True)
            self._emit("state", True, "Synced local OSC state to Sam.py.", result, source="sync")
        elif command == "unlink":
            try:
                result = self._request("POST", "/unlink", payload={}, use_auth=True)
            except Exception:
                result = {"ok": False}
            self._emit("unlinked", True, "Local Sam.py link removed.", result, source="unlink")
        elif command == "recovery_options":
            result = self._request("GET", "/recovery/options", use_auth=True)
            self._emit("recovery_options", True, "Recovery options refreshed.", result, source="recovery_options")
        elif command == "use_recovery":
            result = self._request("POST", "/recovery/use", payload=payload, use_auth=True)
            self._emit("recovery_used", True, str(result.get("message") or "Recovery action completed."), result, source="use_recovery")

    def _worker(self) -> None:
        while not self._stop.is_set():
            command = None
            payload: dict[str, Any] = {}
            try:
                command, payload = self._commands.get(timeout=0.25)
            except queue.Empty:
                pass

            if command == "stop":
                break
            if command:
                try:
                    self._do_command(command, payload)
                except Exception as exc:
                    self._emit(command, False, str(exc), {}, source=command)

            config = self._snapshot_config()
            now = time.monotonic()
            token = str(config.get("token") or "").strip()
            if bool(config.get("enabled", False)) and bool(config.get("auto_poll", True)) and token and now >= self._next_poll_at:
                self._next_poll_at = now + max(0.5, float(config.get("poll_seconds", 2.0)))
                try:
                    result = self._request("GET", "/state", use_auth=True)
                    self._emit("state", True, "Sam.py state refreshed.", result, source="poll")
                except Exception as exc:
                    self._emit("poll", False, str(exc), {}, source="poll")
