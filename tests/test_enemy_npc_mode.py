import copy
import queue
import unittest

from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController
from stories_yggdrasil_osc.sam_client import SamClient


class EnemyModeAndNpcModeTests(unittest.TestCase):
    def test_enemy_mode_is_observed_in_external_input_mode(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["avatar_bridge"]["input_mode"] = "external"
        events = []
        state = CombatState(
            maximum_hp=1000,
            current_hp=1000,
            damage_values=config["combat"]["damage"],
            invulnerability_seconds=1.0,
            critical_hp_percent=0.25,
            status_rules=config["statuses"],
            combat_enabled=True,
        )
        controller = BridgeController(
            config=config,
            state=state,
            send_parameter=lambda *_args: None,
            pulse_parameter=lambda *_args: None,
            event_sink=events.append,
        )
        controller.handle_osc("/avatar/parameters/SoY_IsEnemy", (True,), now=1.0)
        self.assertTrue(controller.telemetry["enemy_mode"])
        self.assertTrue(any(event.metadata.get("enemy_mode") is True for event in events))

    def test_npc_mode_defaults_exist(self):
        self.assertIn("npc_mode", DEFAULT_CONFIG)
        self.assertFalse(DEFAULT_CONFIG["npc_mode"]["enabled"])
        self.assertEqual(DEFAULT_CONFIG["npc_mode"]["enemy_key"], "")

    def test_npc_catalog_client_route(self):
        events = queue.Queue()
        client = SamClient(events, {"base_url": "https://example.invalid", "token": "token"})
        client._request = lambda method, path, **kwargs: {"ok": True, "enemies": [{"key": "wolf", "name": "Wolf"}]}  # type: ignore[method-assign]
        client._do_command("npc_catalog", {})
        event = events.get_nowait()
        self.assertEqual(event.kind, "npc_catalog")
        self.assertTrue(event.ok)
        self.assertEqual(event.data["enemies"][0]["name"], "Wolf")


if __name__ == "__main__":
    unittest.main()
