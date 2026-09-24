import queue
import sys
import time
import types

from stories_yggdrasil_osc.combat_authority import (
    CombatCatalog,
    CombatSourceHint,
    build_incoming_contact_event,
    new_event_id,
)
from stories_yggdrasil_osc.sam_client import SamClient


# Keep controller import independent from an installed python-osc runtime.
pythonosc = types.ModuleType("pythonosc")
pythonosc.dispatcher = types.SimpleNamespace(Dispatcher=object)
pythonosc.osc_server = types.SimpleNamespace(ThreadingOSCUDPServer=object)
pythonosc.udp_client = types.SimpleNamespace(SimpleUDPClient=object)
sys.modules.setdefault("pythonosc", pythonosc)

from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController


def _catalog():
    catalog = CombatCatalog()
    catalog.update({
        "api_version": "0.8.18",
        "capabilities": {
            "stat_aware_pvp": True,
            "stat_aware_npc_vs_player": True,
        },
        "enemies": [
            {
                "key": "malboro_king",
                "name": "Malboro King",
                "avatar_ids": ["avtr-malboro"],
                "osc_mapped": True,
            }
        ],
        "player_identity_bindings": [
            {
                "user_id": "100",
                "char_name": "Clover Edgefield",
                "vrchat_user_id": "usr-clover",
                "avatar_id": "avtr-clover",
            }
        ],
    })
    return catalog


def test_event_ids_are_unique_and_compact():
    a = new_event_id()
    b = new_event_id()
    assert a != b
    assert a.startswith("contact-")
    assert len(a) < 128


def test_npc_to_player_uses_server_bound_avatar_and_never_sends_power():
    payload, reason, metadata = build_incoming_contact_event(
        event_id="evt-1",
        tier="strong",
        source_enemy=True,
        catalog=_catalog(),
        authority_config={"incoming_npc_enemy_name": "Malboro King"},
    )
    assert reason == ""
    assert payload["source"] == {
        "kind": "npc",
        "avatar_id": "avtr-malboro",
        "enemy_name": "Malboro King",
    }
    assert payload["target"] == {"kind": "player"}
    assert payload["action"]["tier"] == "strong"
    assert "power" not in payload["action"]
    assert metadata["identity_source"] == "selected_catalog_npc"


def test_pvp_uses_verified_vrchat_identity_selection():
    payload, reason, metadata = build_incoming_contact_event(
        event_id="evt-2",
        tier="average",
        source_enemy=False,
        catalog=_catalog(),
        authority_config={
            "pvp_source_vrchat_user_id": "usr-clover",
            "pvp_source_avatar_id": "avtr-clover",
        },
    )
    assert reason == ""
    assert payload["source"]["kind"] == "player"
    assert payload["source"]["vrchat_user_id"] == "usr-clover"
    assert payload["source"]["avatar_id"] == "avtr-clover"
    assert metadata["identity_source"] == "selected_verified_player"


def test_unattributed_player_contact_is_refused_instead_of_guessed():
    payload, reason, metadata = build_incoming_contact_event(
        event_id="evt-3",
        tier="average",
        source_enemy=False,
        catalog=_catalog(),
        authority_config={},
    )
    assert payload is None
    assert "unattributed" in reason.casefold()
    assert metadata["identity_source"] == ""


def test_fresh_identity_hint_overrides_manual_source_and_expires():
    hint = CombatSourceHint(
        kind="npc",
        avatar_id="avtr-hinted",
        enemy_name="Hinted Enemy",
        received_at=10.0,
        source="osc_identity_hint",
    )
    payload, reason, metadata = build_incoming_contact_event(
        event_id="evt-4",
        tier="critical",
        source_enemy=True,
        catalog=_catalog(),
        authority_config={"incoming_npc_enemy_name": "Malboro King", "source_hint_ttl_seconds": 2.0},
        hint=hint,
        now=11.0,
    )
    assert reason == ""
    assert payload["source"]["avatar_id"] == "avtr-hinted"
    assert metadata["identity_source"] == "osc_identity_hint"

    payload2, reason2, metadata2 = build_incoming_contact_event(
        event_id="evt-5",
        tier="critical",
        source_enemy=True,
        catalog=_catalog(),
        authority_config={"incoming_npc_enemy_name": "Malboro King", "source_hint_ttl_seconds": 2.0},
        hint=hint,
        now=13.1,
    )
    assert reason2 == ""
    assert payload2["source"]["avatar_id"] == "avtr-malboro"
    assert metadata2["identity_source"] == "selected_catalog_npc"


def test_sam_client_combat_event_keeps_same_id_across_transient_retry(monkeypatch):
    events = queue.Queue()
    client = SamClient(events, {"base_url": "https://example.invalid/api/osc", "token": "token"})
    calls = []

    def fake_request(method, path, *, payload=None, use_auth=False, timeout=6.0):
        calls.append((method, path, dict(payload or {})))
        if len(calls) == 1:
            raise RuntimeError("Sam.py request timed out")
        return {"ok": True, "registered": True, "event_id": payload["event_id"], "result": {}, "target_state": {}}

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(time, "sleep", lambda _value: None)
    client._do_command("combat_event", {"event_id": "same-id", "source": {}, "target": {}, "action": {}})
    assert [call[2]["event_id"] for call in calls] == ["same-id", "same-id"]
    event = events.get_nowait()
    assert event.kind == "combat_event"
    assert event.ok is True
    assert event.data["event_id"] == "same-id"


def test_authoritative_contact_iframe_blocks_repeat_before_server_roundtrip():
    config = __import__("copy").deepcopy(DEFAULT_CONFIG)
    config["sam"].update({"enabled": True, "token": "paired", "authoritative_vrc_damage": True})
    state = CombatState(
        maximum_hp=1000,
        current_hp=1000,
        damage_values=config["combat"]["damage"],
        invulnerability_seconds=1.0,
        critical_hp_percent=0.15,
        status_rules=config["statuses"],
        combat_enabled=True,
    )
    events = []
    controller = BridgeController(
        config=config,
        state=state,
        send_parameter=lambda *_args: None,
        pulse_parameter=lambda *_args: None,
        event_sink=events.append,
    )
    controller.handle_osc("/avatar/parameters/SoY_HitAverage", (True,), 1.0)
    controller.tick(1.2)
    controller.handle_osc("/avatar/parameters/SoY_HitAverage", (False,), 1.25)
    controller.handle_osc("/avatar/parameters/SoY_HitAverage", (True,), 1.30)
    controller.tick(1.5)
    assert len([event for event in events if event.event == "hit_contact"]) == 1
    assert any(event.metadata.get("reason") == "contact_iframe" for event in events)
