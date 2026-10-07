from __future__ import annotations

from types import SimpleNamespace

from stories_yggdrasil_osc.app import StoriesOSCApp
from stories_yggdrasil_osc.app_v0814 import StoriesOSCAppV0814
from stories_yggdrasil_osc.combat_authority import CombatCatalog, CombatSourceHint
from stories_yggdrasil_osc.models import EventResult


class DummyController:
    def __init__(self):
        self.telemetry = {
            "damage_source_enemy": False,
            "enemy_mode": False,
        }

    def consume_damage_alignment(self):
        self.telemetry["damage_source_enemy"] = False


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummySamClient:
    def __init__(self):
        self.events = []
        self.pull_count = 0

    def combat_event(self, payload):
        self.events.append(payload)

    def pull(self):
        self.pull_count += 1


def _catalog() -> CombatCatalog:
    catalog = CombatCatalog()
    catalog.update({
        "api_version": "0.8.18",
        "capabilities": {
            "stat_aware_pvp": True,
            "stat_aware_npc_vs_player": True,
        },
        "enemies": [{
            "key": "sythra",
            "name": "Sythra Velisra",
            "avatar_ids": ["avtr-sythra"],
        }],
        "player_identity_bindings": [],
    })
    return catalog


def _contact_app():
    app = StoriesOSCApp.__new__(StoriesOSCApp)
    app.config = {
        "npc_mode": {"enabled": False},
        "combat_authority": {
            "enabled": True,
            "source_hint_ttl_seconds": 2.0,
            "incoming_npc_enemy_name": "",
            "incoming_npc_avatar_id": "",
            "pvp_source_vrchat_user_id": "",
            "pvp_source_avatar_id": "",
            "unclassified_contacts_are_enemy": True,
        },
    }
    app.combat_catalog = _catalog()
    app.combat_source_hint = CombatSourceHint()
    app.controller = DummyController()
    app.sam_client = DummySamClient()
    app.combat_pending_events = {}
    app.combat_last_result = {}
    app.activity = []
    app._append_activity = lambda category, message: app.activity.append((category, message))
    return app


def test_canonical_friendly_contact_is_not_reclassified_as_npc():
    app = _contact_app()
    result = EventResult(
        True,
        "hit_contact",
        "Average Contact sent to Sam.py.",
        hp_before=100,
        hp_after=100,
        maximum_hp=100,
        metadata={"hit_type": "average", "source": "direct", "source_enemy": False},
    )

    assert app._submit_authoritative_contact(result) is True
    assert not app.sam_client.events
    assert app.combat_last_result["registered"] is False
    assert "Player Contact is unattributed" in app.combat_last_result["message"]
    assert "NPC Contact is unattributed" not in app.combat_last_result["message"]


def test_external_unclassified_contact_keeps_enemy_fallback():
    app = _contact_app()
    result = EventResult(
        True,
        "hit_contact",
        "Average Contact sent to Sam.py.",
        hp_before=100,
        hp_after=100,
        maximum_hp=100,
        metadata={"hit_type": "average", "source": "external", "source_enemy": False},
    )

    assert app._submit_authoritative_contact(result) is True
    assert not app.sam_client.events
    assert "NPC Contact is unattributed" in app.combat_last_result["message"]


def test_enable_npc_mode_commits_runtime_switch_without_attacker(monkeypatch):
    saved = []
    monkeypatch.setattr("stories_yggdrasil_osc.app_v0814.save_config", lambda config: saved.append(config))

    app = StoriesOSCAppV0814.__new__(StoriesOSCAppV0814)
    app.npc_enemy_var = DummyVar("Sythra Velisra")
    app.npc_mode_var = DummyVar(False)
    app.npc_by_name = {
        "Sythra Velisra": {"key": "sythra", "name": "Sythra Velisra"}
    }
    app.config = {
        "npc_mode": {
            "enabled": False,
            "enemy_key": "",
            "enemy_name": "",
            "attacker_mode": "verified",
            "attacker_user_id": "",
            "attacker_char_name": "",
        },
        "parameters": {"enemy_mode": "SoY_IsEnemy"},
    }
    app.controller = DummyController()
    app.sam_client = DummySamClient()
    app.sent = []
    app.activity = []
    app._send_parameter = lambda name, value: app.sent.append((name, value))
    app._schedule_sam_sync = lambda *args, **kwargs: setattr(app, "scheduled_sync", (args, kwargs))
    app._append_activity = lambda category, message: app.activity.append((category, message))
    app._refresh_npc_runtime_status = lambda: None
    app._refresh_npc_attacker_status = lambda: None

    app.enable_npc_mode()

    assert app.config["npc_mode"]["enabled"] is True
    assert app.config["npc_mode"]["enemy_key"] == "sythra"
    assert app.npc_mode_var.get() is True
    assert app.controller.telemetry["enemy_mode"] is True
    assert ("SoY_IsEnemy", True) in app.sent
    assert app.sam_client.pull_count == 1
    assert saved
