import unittest

from stories_yggdrasil_osc.app import StoriesOSCApp


class DummyCombo:
    def __init__(self):
        self.values = []

    def configure(self, **kwargs):
        if "values" in kwargs:
            self.values = list(kwargs["values"])


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class NpcAttackerRosterTests(unittest.TestCase):
    def test_metadata_and_invalid_ids_are_not_loaded(self):
        app = StoriesOSCApp.__new__(StoriesOSCApp)
        app.npc_attacker_roster = []
        app.npc_attackers_by_player = {}
        app.npc_attacker_player_ids = {}
        app.npc_attacker_player_combo = DummyCombo()
        app.npc_attacker_char_combo = DummyCombo()
        app.npc_attacker_player_var = DummyVar("")
        app.npc_attacker_char_var = DummyVar("")
        app.config = {"npc_mode": {"attacker_user_id": ""}}
        app._refresh_npc_attacker_status = lambda: None

        app._load_npc_attacker_roster([
            {"user_id": "dump", "player_label": "Metadata", "character_name": "Bad"},
            {"user_id": "123", "player_label": "Akira — 123", "character_name": "Clover", "active": True, "eligible": True},
            {"user_id": "123", "player_label": "Akira — 123", "character_name": "Alt", "active": False, "eligible": True},
        ])

        self.assertEqual(app.npc_attacker_player_combo.values, ["Akira — 123"])
        self.assertEqual(app.npc_attacker_player_ids["Akira — 123"], "123")

    def test_selected_player_prefers_active_eligible_character(self):
        app = StoriesOSCApp.__new__(StoriesOSCApp)
        app.npc_attackers_by_player = {
            "Akira — 123": [
                {"character_name": "Alt", "active": False, "eligible": True},
                {"character_name": "Clover", "active": True, "eligible": True},
            ]
        }
        app.npc_attacker_player_var = DummyVar("Akira — 123")
        app.npc_attacker_char_var = DummyVar("")
        app.npc_attacker_char_combo = DummyCombo()
        app._refresh_npc_attacker_status = lambda: None
        app._on_npc_attacker_player_selected(None)
        self.assertEqual(app.npc_attacker_char_var.get(), "Clover")
        self.assertEqual(app.npc_attacker_char_combo.values, ["Alt", "Clover"])


if __name__ == "__main__":
    unittest.main()
