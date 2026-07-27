from __future__ import annotations

import queue
import urllib.parse

from stories_yggdrasil_osc.sam_client import SamClient


def _client(**overrides):
    config = {
        "base_url": "https://example.invalid/api/osc",
        "token": "token",
        "enabled": True,
        "auto_poll": True,
        "poll_seconds": 2.0,
        "idle_poll_seconds": 5.0,
        "max_backoff_seconds": 60.0,
    }
    config.update(overrides)
    return SamClient(queue.Queue(), config)


def test_revision_query_uses_last_authoritative_revision():
    client = _client()
    client._last_revision = 42
    path = client._poll_path()
    parsed = urllib.parse.urlparse(path)
    assert parsed.path == "/state"
    assert urllib.parse.parse_qs(parsed.query) == {"after_revision": ["42"]}


def test_sync_bursts_keep_only_the_latest_complete_payload():
    client = _client()
    client.sync({"hp": 100, "sequence": 1})
    client.sync({"hp": 90, "sequence": 2})
    client.sync({"hp": 80, "sequence": 3})

    assert client._commands.qsize() == 1
    command, _payload = client._commands.get_nowait()
    assert command == "sync_latest"
    assert client._take_latest_sync_payload() == {"hp": 80, "sequence": 3}


def test_idle_polling_is_slower_than_active_combat():
    client = _client()
    client._last_combat_enabled = False
    client._last_state_changed_at = 0.0
    assert client._poll_interval(client._snapshot_config()) == 5.0

    client._last_combat_enabled = True
    assert client._poll_interval(client._snapshot_config()) == 2.0


def test_outage_backoff_is_capped():
    client = _client()
    client._last_combat_enabled = False
    client._last_state_changed_at = 0.0
    client._consecutive_poll_failures = 10
    assert client._poll_interval(client._snapshot_config()) == 60.0
