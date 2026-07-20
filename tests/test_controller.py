import copy
import unittest

from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.events = []
        self.sent = []
        self.state = CombatState(
            maximum_hp=1000,
            current_hp=1000,
            damage_values=self.config["combat"]["damage"],
            invulnerability_seconds=0,
            critical_hp_percent=0.25,
            status_rules=self.config["statuses"],
            clear_statuses_when_disabled=True,
            combat_enabled=True,
        )
        self.controller = BridgeController(
            config=self.config,
            state=self.state,
            send_parameter=lambda n, v: self.sent.append((n, v)),
            pulse_parameter=lambda n, v: None,
            event_sink=self.events.append,
        )

    def test_direct_average_hit(self):
        self.controller.handle_osc("/avatar/parameters/SoY_HitAverage", (True,), 1.0)
        self.controller.tick(1.2)
        self.assertEqual(self.state.current_hp, 900)

    def test_compatible_health_is_observed(self):
        self.controller.handle_osc("/avatar/parameters/Health", (0.25,), 2.0)
        self.assertTrue(self.controller.external_detected)
        self.assertEqual(self.state.current_hp, 750)

    def test_combat_toggle_always_accepted(self):
        self.config["avatar_bridge"]["input_mode"] = "external"
        self.controller.reconfigure(self.config)
        self.controller.handle_osc("/avatar/parameters/SoY_CombatEnabled", (False,), 3.0)
        self.assertFalse(self.state.combat_enabled)


    def test_binary_spell_bus_resolves_curaja_id_four(self):
        self.controller.handle_osc("/avatar/parameters/SoY_SpellBit2", (True,), 5.00)
        self.controller.handle_osc("/avatar/parameters/SoY_SpellActive", (True,), 5.01)
        self.controller.tick(5.05)
        self.assertEqual(self.controller.telemetry["spell_type"], 4)
        spell_events = [event for event in self.events if event.metadata.get("spell_type") == 4]
        self.assertEqual(len(spell_events), 1)

    def test_binary_spell_bus_resolves_multiple_bits(self):
        # 127 = 0b01111111
        for bit in range(7):
            self.controller.handle_osc(f"/avatar/parameters/SoY_SpellBit{bit}", (True,), 6.00 + bit * 0.001)
        self.controller.handle_osc("/avatar/parameters/SoY_SpellActive", (True,), 6.02)
        self.controller.tick(6.06)
        self.assertEqual(self.controller.telemetry["spell_type"], 127)

    def test_binary_spell_bus_clears_when_contact_exits(self):
        self.controller.handle_osc("/avatar/parameters/SoY_SpellBit0", (True,), 7.00)
        self.controller.handle_osc("/avatar/parameters/SoY_SpellActive", (True,), 7.01)
        self.controller.tick(7.05)
        self.assertEqual(self.controller.telemetry["spell_type"], 1)
        self.controller.handle_osc("/avatar/parameters/SoY_SpellActive", (False,), 7.10)
        self.assertEqual(self.controller.telemetry["spell_type"], 0)

    def test_contact_family_deduplicates(self):
        self.controller.handle_osc("/avatar/parameters/Hit By Average Attack T0", (True,), 4.0)
        self.controller.handle_osc("/avatar/parameters/Hit By Average Attack T1", (True,), 4.02)
        self.controller.tick(4.2)
        observed = [x for x in self.events if x.event == "external_hit_observed"]
        self.assertEqual(len(observed), 1)


if __name__ == "__main__":
    unittest.main()
