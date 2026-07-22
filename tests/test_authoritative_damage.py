import copy
import sys
import types
import unittest

# Keep import independent from optional python-osc runtime package.
pythonosc = types.ModuleType("pythonosc")
pythonosc.dispatcher = types.SimpleNamespace(Dispatcher=object)
pythonosc.osc_server = types.SimpleNamespace(ThreadingOSCUDPServer=object)
pythonosc.udp_client = types.SimpleNamespace(SimpleUDPClient=object)
sys.modules.setdefault("pythonosc", pythonosc)

from stories_yggdrasil_osc.app import StoriesOSCApp
from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController


class AuthoritativeDamageControllerTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config["sam"].update({"enabled": True, "token": "paired", "authoritative_vrc_damage": True})
        self.events = []
        self.sent = []
        self.pulsed = []
        self.state = CombatState(
            maximum_hp=1000,
            current_hp=1000,
            damage_values=self.config["combat"]["damage"],
            invulnerability_seconds=1.0,
            critical_hp_percent=0.25,
            status_rules=self.config["statuses"],
            clear_statuses_when_disabled=True,
            combat_enabled=True,
        )
        self.controller = BridgeController(
            config=self.config,
            state=self.state,
            send_parameter=lambda n, v: self.sent.append((n, v)),
            pulse_parameter=lambda n, v: self.pulsed.append((n, v)),
            event_sink=self.events.append,
        )

    def test_paired_hit_waits_for_sam_and_does_not_apply_fixed_local_damage(self):
        self.controller.handle_osc("/avatar/parameters/SoY_HitAverage", (True,), 1.0)
        self.controller.tick(1.2)
        self.assertEqual(self.state.current_hp, 1000)
        result = [event for event in self.events if event.event == "hit_contact"][-1]
        self.assertEqual(result.metadata["hit_type"], "average")
        self.assertFalse(result.metadata["source_enemy"])
        self.assertEqual(self.controller.telemetry["hit_event"], "average")

    def test_enemy_alignment_is_captured_with_hit(self):
        self.controller.handle_osc("/avatar/parameters/SoY_DamageSourceEnemy", (True,), 2.00)
        self.controller.handle_osc("/avatar/parameters/SoY_HitStrong", (True,), 2.01)
        self.controller.tick(2.20)
        result = [event for event in self.events if event.event == "hit_contact"][-1]
        self.assertTrue(result.metadata["source_enemy"])
        self.assertTrue(self.controller.telemetry["damage_source_enemy"])

    def test_paired_status_waits_for_sam(self):
        self.controller.handle_osc("/avatar/parameters/SoY_DebuffBurn", (True,), 3.0)
        self.controller.tick(3.1)
        self.assertNotIn("burn", self.state.statuses)
        result = [event for event in self.events if event.event == "status_contact"][-1]
        self.assertEqual(result.metadata["status"], "burn")
        self.assertEqual(self.controller.telemetry["status_event"], "burn")

    def test_external_health_cannot_bypass_authoritative_contact_damage(self):
        self.controller.handle_osc("/avatar/parameters/Health", (0.50,), 4.0)
        self.assertEqual(self.state.current_hp, 1000)
        self.assertTrue(any(event.event == "external_health_observed" for event in self.events))


class DummyState:
    def snapshot(self):
        return {
            "current_hp": 500,
            "maximum_hp": 1000,
            "hp_ratio": 0.5,
            "combat_enabled": True,
            "statuses": {},
        }


class DummyController:
    active_input_mode = "direct"
    telemetry = {
        "enemy_mode": False,
        "healing_source_enemy": False,
        "damage_source_enemy": True,
        "hit_event": "strong",
        "status_event": "",
    }


class DamagePayloadTests(unittest.TestCase):
    def test_hit_payload_uses_damage_alignment_and_is_one_shot(self):
        app = StoriesOSCApp.__new__(StoriesOSCApp)
        app.config = {"sam": {"sync_hp": True, "sync_combat_toggle": True, "sync_statuses": False}, "npc_mode": {}}
        app.state = DummyState()
        app.controller = DummyController()
        app.sam_client_seq = 0
        app.sam_client_session = "damage"
        app.sam_last_event_name = "hit_contact"
        app.sam_last_event_vrc_trigger = True
        app.last_avatar_id = "avatar"
        payload = app._build_sam_sync_payload()
        self.assertEqual(payload["hit_event"], "strong")
        self.assertTrue(payload["source_enemy"])
        self.assertEqual(app.controller.telemetry["hit_event"], "")


if __name__ == "__main__":
    unittest.main()
