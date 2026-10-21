import queue
import unittest

from stories_yggdrasil_osc.npc_runtime import (
    confirmed_npc, passive_hp_sync_allowed, npc_restore_payload, restored_state_matches,
)
from stories_yggdrasil_osc.sam_client import SamClient


def state(key="alexis", hp=0, max_hp=145000):
    return {"profile_mode": "npc", "npc": {"enemy_key": key},
            "character": {"name": "Alexis", "hp": hp, "max_hp": max_hp},
            "sync_result": {"accepted": True, "duplicate": False}}


class NPCHealthIsolationTests(unittest.TestCase):
    def test_passive_hp_allowed_only_for_confirmed_player(self):
        self.assertTrue(passive_hp_sync_allowed({"profile_mode": "player"}, {"enabled": False}))
        self.assertFalse(passive_hp_sync_allowed({"profile_mode": "player"}, {"enabled": True}))
        self.assertFalse(passive_hp_sync_allowed(state(), {"enabled": True}))
        self.assertFalse(passive_hp_sync_allowed(state(), {"enabled": False}))

    def test_requires_server_ack_for_same_npc_key(self):
        self.assertTrue(confirmed_npc(state(), {"enabled": True, "enemy_key": "alexis"}))
        self.assertFalse(confirmed_npc(state(), {"enabled": True, "enemy_key": "other"}))
        self.assertFalse(confirmed_npc({"profile_mode": "player", "npc": {"enemy_key": "alexis"}},
                                       {"enabled": True, "enemy_key": "alexis"}))

    def test_manual_restore_is_explicit_hp_only(self):
        result = npc_restore_payload(state(hp=4363), {"enabled": True, "enemy_key": "alexis"},
                                     client_seq=11, client_session="session", client_version="0.8.22-prebuild.3")
        self.assertEqual(result["hp"], 145000)
        self.assertTrue(result["npc_mode"])
        self.assertFalse(result["vrc_trigger"])
        self.assertEqual(result["client_event"], "npc_restore_hp")
        self.assertNotIn("mp", result)
        self.assertNotIn("npc_attacker_user_id", result)

    def test_restoration_rejected_until_ack_and_if_already_full(self):
        for item, cfg in [
            ({"profile_mode": "player"}, {"enabled": True, "enemy_key": "alexis"}),
            (state(key="other"), {"enabled": True, "enemy_key": "alexis"}),
            (state(hp=145000), {"enabled": True, "enemy_key": "alexis"}),
        ]:
            with self.assertRaises(ValueError):
                npc_restore_payload(item, cfg, client_seq=1, client_session="x", client_version="v1")

    def test_server_ack_requires_matching_hp_key_and_nonduplicate(self):
        self.assertTrue(restored_state_matches(state(hp=145000), key="alexis"))
        self.assertFalse(restored_state_matches(state(hp=0), key="alexis"))
        self.assertFalse(restored_state_matches(state(key="other", hp=145000), key="alexis"))
        duplicate = state(hp=145000)
        duplicate["sync_result"]["duplicate"] = True
        self.assertFalse(restored_state_matches(duplicate, key="alexis"))

    def test_restore_client_reuses_authenticated_sync_route(self):
        events = queue.Queue()
        client = SamClient(events, {"base_url": "https://example.invalid", "token": "token"})
        calls = []
        def fake(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"state": state(hp=145000)}
        client._request = fake
        client._do_command("npc_restore_hp", {"npc_enemy_key": "alexis", "hp": 145000})
        event = events.get_nowait()
        self.assertTrue(event.ok)
        self.assertEqual(event.kind, "npc_restore_hp")
        self.assertEqual(calls[0][:2], ("POST", "/sync"))
        self.assertTrue(calls[0][2]["use_auth"])


if __name__ == "__main__":
    unittest.main()
