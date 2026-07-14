from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pythonosc import dispatcher, osc_server, udp_client


@dataclass(frozen=True)
class OSCEvent:
    address: str
    values: tuple[Any, ...]
    received_at_wall: float
    received_at_monotonic: float
    kind: str = "message"


class OSCService:
    def __init__(self, *, listen_ip: str, listen_port: int, vrchat_ip: str, vrchat_port: int, event_queue: queue.Queue[OSCEvent]) -> None:
        self.listen_ip = str(listen_ip)
        self.listen_port = int(listen_port)
        self.vrchat_ip = str(vrchat_ip)
        self.vrchat_port = int(vrchat_port)
        self.event_queue = event_queue
        self._server: osc_server.ThreadingOSCUDPServer | None = None
        self._thread: threading.Thread | None = None
        self._client = udp_client.SimpleUDPClient(self.vrchat_ip, self.vrchat_port)
        self._running = False
        self._lock = threading.RLock()
        self.last_received_monotonic = 0.0
        self.received_count = 0
        self.last_received_address = ""

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def _default_handler(self, address: str, *values: Any) -> None:
        mono = time.monotonic()
        self.last_received_monotonic = mono
        self.received_count += 1
        self.last_received_address = str(address)
        self.event_queue.put(OSCEvent(address, tuple(values), time.time(), mono))

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            disp = dispatcher.Dispatcher()
            disp.set_default_handler(self._default_handler)
            self._server = osc_server.ThreadingOSCUDPServer((self.listen_ip, self.listen_port), disp)
            self._thread = threading.Thread(target=self._server.serve_forever, name="SoY-OSC-Listener", daemon=True)
            self._running = True
            self._thread.start()
        self.event_queue.put(OSCEvent("/soy/system/listener", (True, self.listen_ip, self.listen_port), time.time(), time.monotonic(), "system"))

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._running = False
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
        self.event_queue.put(OSCEvent("/soy/system/listener", (False,), time.time(), time.monotonic(), "system"))

    def reconfigure(self, *, listen_ip: str, listen_port: int, vrchat_ip: str, vrchat_port: int, restart: bool = True) -> None:
        was_running = self.running
        if was_running:
            self.stop()
        self.listen_ip = str(listen_ip)
        self.listen_port = int(listen_port)
        self.vrchat_ip = str(vrchat_ip)
        self.vrchat_port = int(vrchat_port)
        self._client = udp_client.SimpleUDPClient(self.vrchat_ip, self.vrchat_port)
        if restart and was_running:
            self.start()

    def send(self, address: str, value: Any) -> None:
        if not str(address).startswith("/"):
            raise ValueError("OSC address must begin with '/'.")
        self._client.send_message(str(address), value)

    def send_avatar_parameter(self, parameter: str, value: Any) -> None:
        name = str(parameter).strip()
        if not name:
            return
        self.send(f"/avatar/parameters/{name}", value)

    def pulse_avatar_parameter(self, parameter: str, duration: float = 0.12) -> None:
        self.send_avatar_parameter(parameter, True)

        def reset() -> None:
            try:
                self.send_avatar_parameter(parameter, False)
            except Exception:
                pass

        timer = threading.Timer(max(0.03, float(duration)), reset)
        timer.daemon = True
        timer.start()

    def loopback_test(self) -> str:
        token = uuid.uuid4().hex[:10]
        client = udp_client.SimpleUDPClient(self.listen_ip, self.listen_port)
        client.send_message(f"/soy/selftest/{token}", token)
        return token
