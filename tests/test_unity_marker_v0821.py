from __future__ import annotations

import sys
import types

pythonosc = types.ModuleType("pythonosc")
pythonosc.dispatcher = types.SimpleNamespace(Dispatcher=object)
pythonosc.osc_server = types.SimpleNamespace(ThreadingOSCUDPServer=object)
pythonosc.udp_client = types.SimpleNamespace(SimpleUDPClient=object)
sys.modules.setdefault("pythonosc", pythonosc)

from stories_yggdrasil_osc.avatar_compatibility import (
    MAX_UNITY_PROTOCOL,
    MIN_UNITY_PROTOCOL,
    UnityAvatarCompatibility,
)


def publish_current(tracker: UnityAvatarCompatibility, *, protocol: int = 20, schema: bool = True) -> None:
    for name, value in (
        ("SoY_UnityToolPresent", True),
        ("SoY_UnityToolMajor", 0),
        ("SoY_UnityToolMinor", 5),
        ("SoY_UnityToolPatch", 10),
        ("SoY_UnityToolTB", 17),
        ("SoY_UnityToolTBRevision", 0),
        ("SoY_ProtocolVersion", protocol),
        ("SoY_UnitySchemaValid", schema),
    ):
        assert tracker.observe_parameter(name, value)


def test_current_tb17_protocol20_marker_is_compatible() -> None:
    tracker = UnityAvatarCompatibility()
    publish_current(tracker)
    assert tracker.compatible
    assert tracker.status == "compatible"
    assert tracker.tool_version == "v0.5.10 TB17"
    assert tracker.protocol == 20


def test_protocol19_requires_tb17_migration() -> None:
    tracker = UnityAvatarCompatibility()
    publish_current(tracker, protocol=19)
    assert not tracker.compatible
    assert tracker.status == "update_required_avatar"
    assert "20" in tracker.block_reason()


def test_future_protocol_requires_desktop_update() -> None:
    tracker = UnityAvatarCompatibility()
    publish_current(tracker, protocol=MAX_UNITY_PROTOCOL + 1)
    assert tracker.status == "update_required_desktop"


def test_invalid_schema_fails_closed() -> None:
    tracker = UnityAvatarCompatibility()
    publish_current(tracker, schema=False)
    assert tracker.status == "schema_invalid"
    assert not tracker.compatible


def test_external_aliases_are_not_protocol_gated() -> None:
    tracker = UnityAvatarCompatibility()
    for name in ("Health", "Hit By Weak Attack T0", "Sword", "Weapon", "Hands"):
        assert not tracker.is_protected_soy_parameter(name)


def test_protocol20_external_source_parameter_is_protected() -> None:
    tracker = UnityAvatarCompatibility()
    assert tracker.is_protected_soy_parameter("SoY_ExternalDamageSource")


def test_unmarked_direct_soy_input_fails_closed() -> None:
    tracker = UnityAvatarCompatibility()
    tracker.note_protected_input()
    assert tracker.status == "update_required_avatar"


def test_protocol20_marker_tolerates_present_false_startup_race() -> None:
    tracker = UnityAvatarCompatibility()
    publish_current(tracker)
    tracker.observe_parameter("SoY_UnityToolPresent", False)
    assert tracker.compatible
    assert tracker.status == "compatible"


def test_protocol20_incomplete_marker_reports_incomplete_not_unsupported() -> None:
    tracker = UnityAvatarCompatibility()
    tracker.observe_parameter("SoY_ProtocolVersion", 20)
    tracker.note_protected_input()
    assert tracker.status == "update_required_avatar"
    reason = tracker.block_reason()
    assert "incomplete" in reason.lower()
    assert "unsupported" not in reason.lower()


def test_tb17_1_beacon_recovers_late_desktop_start() -> None:
    tracker = UnityAvatarCompatibility()
    tracker.note_protected_input()
    assert not tracker.compatible
    assert tracker.observe_parameter("SoY_UnityMarkerBeacon", 117)
    assert tracker.compatible
    assert tracker.tool_version == "v0.5.10 TB17.1"
    assert tracker.protocol == 20
    assert tracker.schema_valid is True


def test_tb17_1_beacon_alternates_without_losing_compatibility() -> None:
    tracker = UnityAvatarCompatibility()
    for value in (117, 118, 117, 118):
        assert tracker.observe_parameter("SoY_UnityMarkerBeacon", value)
        assert tracker.compatible


def test_unknown_beacon_value_does_not_bypass_fail_closed() -> None:
    tracker = UnityAvatarCompatibility()
    tracker.note_protected_input()
    tracker.observe_parameter("SoY_UnityMarkerBeacon", 42)
    assert not tracker.compatible
