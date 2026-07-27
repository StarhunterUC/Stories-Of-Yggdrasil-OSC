from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.parse
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
    """Background HTTP client for Sam.py's restricted OSC API.

    Phase 1 optimizations:
    - coalesces pending sync payloads;
    - uses revision-aware state polling;
    - polls more slowly while idle;
    - exponentially backs off during outages;
    - suppresses duplicate error events during a failure storm.
    """

    def __init__(self, event_queue: queue.Queue[SamEvent], config: dict[str, Any]) -> None:
        self.event_queue = event_queue
        self._commands: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._config = dict(config)
        self._next_poll_at = 0.0

        self._last_revision = -1
        self._last_combat_enabled = False
        self._last_state_changed_at = 0.0
        self._consecutive_poll_failures = 0
        self._last_poll_error = ""
        self._last_poll_error_emit_at = 0.0

        self._latest_sync_payload: dict[str, Any] | None = None
        self._sync_marker_queued = False

    def reconfigure(self, config: dict[str, Any]) -> None:
        with self._lock:
            old_token = str(self._config.get("token") or "")
            new_token = str(config.get("token") or "")
            self._config = dict(config)
            self._next_poll_at = 0.0
            if old_token != new_token:
                self._last_revision = -1
                self._last_combat_enabled = False
                self._consecutive_poll_failures = 0
                self._last_poll_error = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker,
            name="StoriesSamBridge",
            daemon=True,
        )
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
        # OSC bursts may schedule several state pushes before the previous HTTP
        # request finishes. Keep only the newest complete payload.
        with self._lock:
            self._latest_sync_payload = dict(payload)
            if self._sync_marker_queued:
                return
            self._sync_marker_queued = True
        self._commands.put(("sync_latest", {}))

    def unlink(self) -> None:
        self._commands.put(("unlink", {}))

    def recovery_options(self) -> None:
        self._commands.put(("recovery_options", {}))

    def npc_catalog(self) -> None:
        self._commands.put(("npc_catalog", {}))

    def use_recovery(self, kind: str, name: str) -> None:
        self._commands.put(
            ("use_recovery", {"kind": str(kind), "name": str(name)})
        )

    def _take_latest_sync_payload(self) -> dict[str, Any] | None:
        with self._lock:
            payload = self._latest_sync_payload
            self._latest_sync_payload = None
            self._sync_marker_queued = False
        return dict(payload) if isinstance(payload, dict) else None

    def _snapshot_config(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._config)

    @staticmethod
    def _base_url(config: dict[str, Any]) -> str:
        return str(
            config.get("base_url")
            or "https://admin.storiesofyggdrasil.com/api/osc"
        ).strip().rstrip("/")

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

    def _emit(
        self,
        kind: str,
        ok: bool,
        message: str,
        data: dict[str, Any] | None = None,
        *,
        source: str = "",
    ) -> None:
        self.event_queue.put(SamEvent(kind, ok, message, data or {}, source))

    def _remember_state_response(self, result: dict[str, Any]) -> None:
        state = result.get("state") if isinstance(result.get("state"), dict) else {}
        if not state:
            return
        revision = int(state.get("revision", result.get("revision", 0)) or 0)
        if revision != self._last_revision:
            self._last_state_changed_at = time.monotonic()
        self._last_revision = max(self._last_revision, revision)
        self._last_combat_enabled = bool(
            state.get("combat_enabled", self._last_combat_enabled)
        )

    def _do_command(self, command: str, payload: dict[str, Any]) -> None:
        if command == "pair":
            result = self._request("POST", "/pair", payload=payload)
            state = result.get("state")
            if isinstance(state, dict):
                self._remember_state_response({"state": state})
            self._emit(
                "paired",
                True,
                "Device paired with Sam.py.",
                result,
                source="pair",
            )
        elif command == "test":
            health = self._request("GET", "/health")
            token = str(self._snapshot_config().get("token") or "").strip()
            if token:
                state = self._request("GET", "/state", use_auth=True)
                self._remember_state_response(state)
                health["state_response"] = state
            self._emit(
                "test",
                True,
                "Sam.py connection test passed.",
                health,
                source="test",
            )
        elif command == "pull":
            result = self._request("GET", "/state", use_auth=True)
            self._remember_state_response(result)
            self._emit(
                "state",
                True,
                "Pulled active character state from Sam.py.",
                result,
                source="pull",
            )
        elif command in {"sync", "sync_latest"}:
            sync_payload = (
                self._take_latest_sync_payload()
                if command == "sync_latest"
                else payload
            )
            if not isinstance(sync_payload, dict):
                return
            result = self._request(
                "POST",
                "/sync",
                payload=sync_payload,
                use_auth=True,
            )
            self._remember_state_response(result)
            self._emit(
                "state",
                True,
                "Synced local OSC state to Sam.py.",
                result,
                source="sync",
            )
        elif command == "unlink":
            try:
                result = self._request(
                    "POST",
                    "/unlink",
                    payload={},
                    use_auth=True,
                )
            except Exception:
                result = {"ok": False}
            self._last_revision = -1
            self._emit(
                "unlinked",
                True,
                "Local Sam.py link removed.",
                result,
                source="unlink",
            )
        elif command == "recovery_options":
            result = self._request("GET", "/recovery/options", use_auth=True)
            self._emit(
                "recovery_options",
                True,
                "Recovery options refreshed.",
                result,
                source="recovery_options",
            )
        elif command == "npc_catalog":
            result = self._request("GET", "/npc/catalog", use_auth=True)
            self._emit(
                "npc_catalog",
                True,
                "NPC roster refreshed.",
                result,
                source="npc_catalog",
            )
        elif command == "use_recovery":
            result = self._request(
                "POST",
                "/recovery/use",
                payload=payload,
                use_auth=True,
            )
            state = result.get("state")
            if isinstance(state, dict):
                self._remember_state_response({"state": state})
            self._emit(
                "recovery_used",
                True,
                str(result.get("message") or "Recovery action completed."),
                result,
                source="use_recovery",
            )

    def _poll_interval(self, config: dict[str, Any]) -> float:
        active_seconds = max(
            0.75,
            float(config.get("poll_seconds", 2.0) or 2.0),
        )
        idle_seconds = max(
            active_seconds,
            float(config.get("idle_poll_seconds", 5.0) or 5.0),
        )
        recently_changed = (
            self._last_state_changed_at > 0.0
            and time.monotonic() - self._last_state_changed_at <= 15.0
        )
        base = (
            active_seconds
            if self._last_combat_enabled or recently_changed
            else idle_seconds
        )
        max_backoff = max(
            base,
            float(config.get("max_backoff_seconds", 60.0) or 60.0),
        )
        if self._consecutive_poll_failures <= 0:
            return base
        return min(
            max_backoff,
            base * (2 ** min(self._consecutive_poll_failures, 6)),
        )

    def _poll_path(self) -> str:
        if self._last_revision < 0:
            return "/state"
        query = urllib.parse.urlencode(
            {"after_revision": int(self._last_revision)}
        )
        return f"/state?{query}"

    def _handle_poll_failure(self, exc: Exception) -> None:
        self._consecutive_poll_failures += 1
        message = str(exc)
        now = time.monotonic()
        # Emit immediately when the error changes, otherwise no more than once
        # per minute. This prevents one outage from flooding events.log.
        should_emit = (
            message != self._last_poll_error
            or now - self._last_poll_error_emit_at >= 60.0
        )
        self._last_poll_error = message
        if should_emit:
            self._last_poll_error_emit_at = now
            self._emit("poll", False, message, {}, source="poll")

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
                    self._emit(
                        command,
                        False,
                        str(exc),
                        {},
                        source=command,
                    )

            config = self._snapshot_config()
            now = time.monotonic()
            token = str(config.get("token") or "").strip()
            enabled = (
                bool(config.get("enabled", False))
                and bool(config.get("auto_poll", True))
                and bool(token)
            )
            if not enabled or now < self._next_poll_at:
                continue

            try:
                result = self._request(
                    "GET",
                    self._poll_path(),
                    use_auth=True,
                )
                self._consecutive_poll_failures = 0
                self._last_poll_error = ""
                changed = bool(result.get("changed", True))
                if changed and isinstance(result.get("state"), dict):
                    self._remember_state_response(result)
                    self._emit(
                        "state",
                        True,
                        "Sam.py state refreshed.",
                        result,
                        source="poll",
                    )
                elif result.get("revision") is not None:
                    self._last_revision = max(
                        self._last_revision,
                        int(result.get("revision", 0) or 0),
                    )
            except Exception as exc:
                self._handle_poll_failure(exc)
            finally:
                self._next_poll_at = (
                    time.monotonic() + self._poll_interval(config)
                )
