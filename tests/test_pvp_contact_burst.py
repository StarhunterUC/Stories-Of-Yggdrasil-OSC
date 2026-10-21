import unittest
from types import SimpleNamespace
from unittest.mock import patch

from stories_yggdrasil_osc.app import StoriesOSCApp


class PvPBurstSuppressionTests(unittest.TestCase):
    def setUp(self):
        self.app = StoriesOSCApp.__new__(StoriesOSCApp)
        self.app.avatar_compatibility = SimpleNamespace(protocol=21)
        self.app.config = {"npc_mode": {"enabled": False}}
        self.app.remote_state = {"profile_mode": "player"}
        self.app.state = SimpleNamespace(combat_enabled=True)
        self.sent = []
        self.activity = []
        self.app.sam_client = SimpleNamespace(pvp_attack_attempt=lambda tier, eid: self.sent.append((tier, eid)))
        self.app._append_activity = lambda kind, message: self.activity.append((kind, message))
        self.result = SimpleNamespace(metadata={"tier": "strong"})

    def test_same_swing_contacts_submit_once(self):
        with patch("stories_yggdrasil_osc.app.time.monotonic", side_effect=[20.0, 20.1, 20.2, 21.0]):
            for _ in range(4):
                self.assertTrue(self.app._submit_pvp_attack_attempt(self.result))
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0][0], "strong")

    def test_different_tiers_not_misrepresented(self):
        with patch("stories_yggdrasil_osc.app.time.monotonic", side_effect=[20.0, 20.1]):
            self.app._submit_pvp_attack_attempt(self.result)
            self.app._submit_pvp_attack_attempt(SimpleNamespace(metadata={"tier": "weak"}))
        self.assertEqual([t for t, _ in self.sent], ["strong", "weak"])

    def test_npc_mode_and_pending_player_confirmation_block_attempts(self):
        self.app.config["npc_mode"]["enabled"] = True
        with patch("stories_yggdrasil_osc.app.time.monotonic", return_value=20.0):
            self.app._submit_pvp_attack_attempt(self.result)
        self.app.config["npc_mode"]["enabled"] = False
        self.app.remote_state = {"profile_mode": "npc"}
        with patch("stories_yggdrasil_osc.app.time.monotonic", return_value=21.0):
            self.app._submit_pvp_attack_attempt(self.result)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.activity), 1)

    def test_combat_disabled_blocks_outgoing_pvp(self):
        self.app.state.combat_enabled = False
        with patch("stories_yggdrasil_osc.app.time.monotonic", return_value=20.0):
            self.app._submit_pvp_attack_attempt(self.result)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
