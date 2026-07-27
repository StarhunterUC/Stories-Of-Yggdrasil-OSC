import unittest

from stories_yggdrasil_osc.app import StoriesOSCApp


class DummyState:
    def snapshot(self):
        return {"current_hp": 500, "maximum_hp": 1000, "hp_ratio": 0.5, "combat_enabled": True, "statuses": {}}


class DummyController:
    active_input_mode = "direct"
    telemetry = {
        "enemy_mode": True,
        "healing_source_enemy": False,
        "damage_source_enemy": False,
        "hit_event": "average",
        "status_event": "",
    }

    def consume_damage_alignment(self):
        self.telemetry["damage_source_enemy"] = False


class NpcAttackerIdentityTests(unittest.TestCase):
    def make_app(self, npc):
        app = StoriesOSCApp.__new__(StoriesOSCApp)
        app.config = {"sam": {"sync_hp": True, "sync_combat_toggle": True, "sync_statuses": False}, "npc_mode": npc}
        app.state = DummyState()
        app.controller = DummyController()
        app.sam_client_seq = 0
        app.sam_client_session = "npc-attacker"
        app.sam_last_event_name = "hit_contact"
        app.sam_last_event_vrc_trigger = True
        app.last_avatar_id = "avatar"
        return app

    def test_verified_identity_is_sent_without_stats(self):
        app = self.make_app({
            "enabled": True,
            "enemy_key": "wolf",
            "attacker_mode": "verified",
            "attacker_user_id": "123456789",
            "attacker_char_name": "Clover Edgefield",
        })
        payload = app._build_sam_sync_payload()
        self.assertEqual(payload["npc_attacker_user_id"], "123456789")
        self.assertEqual(payload["npc_attacker_char_name"], "Clover Edgefield")
        self.assertNotIn("atk", payload)
        self.assertNotIn("mag", payload)
        self.assertNotIn("level", payload)

    def test_fallback_clears_stale_server_identity(self):
        app = self.make_app({
            "enabled": True,
            "enemy_key": "wolf",
            "attacker_mode": "fallback",
            "attacker_user_id": "123456789",
            "attacker_char_name": "Clover Edgefield",
        })
        payload = app._build_sam_sync_payload()
        self.assertEqual(payload["npc_attacker_user_id"], "")
        self.assertEqual(payload["npc_attacker_char_name"], "")


if __name__ == "__main__":
    unittest.main()
