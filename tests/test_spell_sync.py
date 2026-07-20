import sys
import types
import unittest

# Keep this unit test independent from the optional runtime OSC dependency.
pythonosc = types.ModuleType("pythonosc")
pythonosc.dispatcher = types.SimpleNamespace(Dispatcher=object)
pythonosc.osc_server = types.SimpleNamespace(ThreadingOSCUDPServer=object)
pythonosc.udp_client = types.SimpleNamespace(SimpleUDPClient=object)
sys.modules.setdefault("pythonosc", pythonosc)

from stories_yggdrasil_osc.app import StoriesOSCApp


class DummyState:
    def snapshot(self):
        return {
            "current_hp": 500, "maximum_hp": 1000, "hp_ratio": 0.5,
            "combat_enabled": True, "statuses": {},
        }


class DummyController:
    active_input_mode = "direct"
    telemetry = {
        "spell_type": 2,
        "technick_type": 5,
        "item_type": 4,
        "enemy_mode": False,
        "healing_source_enemy": False,
        "hit_event": "",
    }


class SpellSyncTests(unittest.TestCase):
    def test_spell_id_is_one_shot_in_payload(self):
        app = StoriesOSCApp.__new__(StoriesOSCApp)
        app.config = {"sam": {"sync_hp": True, "sync_combat_toggle": True, "sync_statuses": False}}
        app.state = DummyState()
        app.controller = DummyController()
        app.sam_client_seq = 0
        app.sam_client_session = "test"
        app.sam_last_event_name = "spell_contact"
        app.sam_last_event_vrc_trigger = True
        app.last_avatar_id = "avatar"
        payload = app._build_sam_sync_payload()
        self.assertEqual(payload["spell_type"], 2)
        self.assertEqual(payload["technick_type"], 5)
        self.assertEqual(payload["item_type"], 4)
        self.assertEqual(app.controller.telemetry["spell_type"], 0)
        self.assertEqual(app.controller.telemetry["technick_type"], 0)
        self.assertEqual(app.controller.telemetry["item_type"], 0)

    def test_local_action_ids_are_one_shot_in_payload(self):
        app = StoriesOSCApp.__new__(StoriesOSCApp)
        app.config = {"sam": {"sync_hp": True, "sync_combat_toggle": True, "sync_statuses": False}}
        app.state = DummyState()
        controller = DummyController()
        controller.telemetry = dict(controller.telemetry)
        controller.telemetry.update({
            "spell_cast_type": 2,
            "technick_use_type": 1,
            "item_use_type": 4,
        })
        app.controller = controller
        app.sam_client_seq = 0
        app.sam_client_session = "test-local"
        app.sam_last_event_name = "spell_cast"
        app.sam_last_event_vrc_trigger = True
        app.last_avatar_id = "avatar"
        payload = app._build_sam_sync_payload()
        self.assertEqual(payload["spell_cast_type"], 2)
        self.assertEqual(payload["technick_use_type"], 1)
        self.assertEqual(payload["item_use_type"], 4)
        self.assertEqual(controller.telemetry["spell_cast_type"], 0)
        self.assertEqual(controller.telemetry["technick_use_type"], 0)
        self.assertEqual(controller.telemetry["item_use_type"], 0)


if __name__ == "__main__":
    unittest.main()
