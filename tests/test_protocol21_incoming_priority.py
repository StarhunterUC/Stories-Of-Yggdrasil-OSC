import copy
import unittest

from stories_yggdrasil_osc.avatar_compatibility import UnityAvatarCompatibility
from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController


class IncomingPvpPathTests(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(DEFAULT_CONFIG)
        self.cfg["sam"].update({"enabled": True, "token": "paired", "authoritative_vrc_damage": True})
        self.events = []
        self.state = CombatState(
            maximum_hp=1000, current_hp=1000,
            damage_values=self.cfg["combat"]["damage"],
            invulnerability_seconds=1.0, critical_hp_percent=0.15,
            status_rules=self.cfg["statuses"],
            clear_statuses_when_disabled=True, combat_enabled=True,
        )
        self.c = BridgeController(
            config=self.cfg, state=self.state,
            send_parameter=lambda *_: None,
            pulse_parameter=lambda *_: None, event_sink=self.events.append,
        )

    def _hits(self):
        return [e for e in self.events if e.event == "hit_contact"]

    def test_old_avatar_stays_external_after_health_detected(self):
        self.c.handle_osc("/avatar/parameters/Healthbar", (True,), 1.0)
        self.c.handle_osc("/avatar/parameters/SoY_HitStrong", (True,), 2.0)
        self.c.tick(2.3)
        self.assertEqual(self._hits(), [])

    def test_verified_tb182_native_strong_survives_external_detection(self):
        self.c.prefer_native_protocol21_hits = True
        self.c.handle_osc("/avatar/parameters/Healthbar", (True,), 1.0)
        self.c.handle_osc("/avatar/parameters/SoY_ExternalDamageSource", (True,), 1.95)
        self.c.handle_osc("/avatar/parameters/SoY_HitStrong", (True,), 2.0)
        self.c.tick(2.3)
        self.assertEqual(len(self._hits()), 1)
        self.assertEqual(self._hits()[0].metadata["hit_type"], "strong")
        self.assertEqual(self._hits()[0].metadata["source"], "direct")
        self.assertFalse(self._hits()[0].metadata["external_damage_source"])

    def test_external_average_remains_external_even_when_native_prioritized(self):
        self.c.prefer_native_protocol21_hits = True
        self.c.handle_osc("/avatar/parameters/SoY_ExternalHitAverage", (True,), 1.0)
        self.c.tick(1.3)
        self.assertEqual(len(self._hits()), 1)
        self.assertEqual(self._hits()[0].metadata["source"], "external")

    def test_explicit_external_mode_keeps_existing_semantics(self):
        self.cfg["avatar_bridge"]["input_mode"] = "external"
        self.c.reconfigure(self.cfg)
        self.c.prefer_native_protocol21_hits = True
        self.c.handle_osc("/avatar/parameters/SoY_HitStrong", (True,), 1.0)
        self.c.tick(1.3)
        self.assertEqual(self._hits(), [])

    def test_marker_beacon_does_not_downgrade_tb182(self):
        marker = UnityAvatarCompatibility()
        for name,val in (
            ("SoY_UnityToolTB",18), ("SoY_ProtocolVersion",21),
            ("SoY_UnityToolTBRevision",2), ("SoY_UnitySchemaValid",True),
        ):
            marker.observe_parameter(name,val)
        marker.observe_parameter("SoY_UnityMarkerBeacon",121)
        self.assertEqual(marker.values["tb_revision"],2)
        self.assertTrue(marker.supports_isolated_native_hits)
        marker.observe_parameter("SoY_UnityMarkerBeacon",122)
        self.assertTrue(marker.supports_isolated_native_hits)

    def test_tb180_beacon_alone_is_not_approved_for_isolated_native(self):
        marker=UnityAvatarCompatibility()
        marker.observe_parameter("SoY_UnityMarkerBeacon",121)
        self.assertFalse(marker.supports_isolated_native_hits)


if __name__ == "__main__":
    unittest.main()
