from __future__ import annotations

import queue
import sys
import types
from unittest.mock import patch

import pytest

# Keep this unit test independent from the optional runtime OSC dependency.
pythonosc = types.ModuleType("pythonosc")
pythonosc.dispatcher = types.SimpleNamespace(Dispatcher=object)
pythonosc.osc_server = types.SimpleNamespace(ThreadingOSCUDPServer=object)
pythonosc.udp_client = types.SimpleNamespace(SimpleUDPClient=object)
sys.modules.setdefault("pythonosc", pythonosc)

from stories_yggdrasil_osc.app import StoriesOSCApp
from stories_yggdrasil_osc.sam_client import SamClient


def _client():
    return SamClient(queue.Queue(), {
        "base_url": "https://admin.storiesofyggdrasil.com/api/osc",
        "token": "token",
        "enabled": True,
        "auto_poll": True,
        "poll_seconds": 2.0,
        "idle_poll_seconds": 5.0,
        "max_backoff_seconds": 10.0,
    })


def test_complete_state_rebases_revision_after_sam_restart():
    client = _client()
    client._last_revision = 42
    client._remember_state_response({"state": {"revision": 3, "combat_enabled": False}})
    assert client._last_revision == 3
    assert "after_revision=3" in client._poll_path()


def test_lower_conditional_revision_is_recognized_as_new_server_epoch():
    client = _client()
    client._last_revision = 42
    assert client._revision_epoch_rolled_back(3) is True
    assert client._revision_epoch_rolled_back(42) is False
    assert client._revision_epoch_rolled_back(43) is False


def test_unchanged_poll_heartbeat_marks_link_as_successful_without_fake_state():
    client = _client()
    client._last_revision = 12
    client._emit_poll_heartbeat({"revision": 12, "api_version": "0.8.16"})
    event = client.event_queue.get_nowait()
    assert event.kind == "heartbeat"
    assert event.ok is True
    assert event.data["revision"] == 12
    assert event.data["api_version"] == "0.8.16"


class _FakeRedirectResponse:
    headers = {"Content-Type": "text/html"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self):
        return "https://storiesofyggdrasil.com/maintenance/"

    def read(self):
        return b"<html>maintenance</html>"


def test_html_maintenance_redirect_is_treated_as_transport_failure():
    client = _client()
    with patch("urllib.request.urlopen", return_value=_FakeRedirectResponse()):
        with pytest.raises(RuntimeError, match="redirected outside its API endpoint"):
            client._request("GET", "/health")


def test_polled_state_is_deferred_while_local_sync_is_unacknowledged():
    app = StoriesOSCApp.__new__(StoriesOSCApp)
    app.config = {"sam": {"pull_remote_changes": True}}
    app.sam_local_dirty = True
    app.sam_sync_inflight = False
    app.sam_pending_remote_state = None
    app.remote_state = {"revision": 7, "character": {"name": "Old"}}
    app.remote_character = {"name": "Old"}

    incoming = {"revision": 8, "character": {"name": "New"}}
    app._apply_sam_state(incoming, source="poll", force=False)

    assert app.sam_pending_remote_state == incoming
    assert app.remote_state["revision"] == 7
    assert app.remote_character["name"] == "Old"
