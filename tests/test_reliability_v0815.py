from __future__ import annotations

import queue
import time

from stories_yggdrasil_osc.sam_client import SamClient


def _client():
    return SamClient(queue.Queue(), {
        "base_url": "https://example.invalid/api/osc",
        "token": "token",
        "enabled": True,
        "auto_poll": True,
        "poll_seconds": 2.0,
        "idle_poll_seconds": 5.0,
        "max_backoff_seconds": 60.0,  # legacy config must still be capped
    })


def test_poll_after_failure_forces_full_authoritative_state():
    client = _client()
    client._last_revision = 42
    client._consecutive_poll_failures = 1
    assert client._poll_path() == "/state"


def test_failed_sync_payload_is_retained_for_retry():
    client = _client()
    payload = {"hp": 321, "client_seq": 7}
    client._restore_failed_sync(payload)
    assert client._latest_sync_payload == payload
    assert client._sync_retry_at > time.monotonic()


def test_newer_sync_payload_wins_over_failed_older_payload():
    client = _client()
    client._latest_sync_payload = {"hp": 200, "client_seq": 8}
    client._restore_failed_sync({"hp": 300, "client_seq": 7})
    assert client._latest_sync_payload == {"hp": 200, "client_seq": 8}


def test_legacy_sixty_second_backoff_is_never_used():
    client = _client()
    client._consecutive_poll_failures = 20
    assert client._poll_interval(client._snapshot_config()) <= 15.0
