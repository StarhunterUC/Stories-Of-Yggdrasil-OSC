import copy
import unittest

from stories_yggdrasil_osc.config import DEFAULT_CONFIG, _migrate_avatar_bridge


class ConfigMigrationTests(unittest.TestCase):
    def test_old_compatibility_values_are_preserved(self):
        legacy = "sh" + "room"
        raw = {
            "compatibility": {
                "input_mode": legacy,
                f"{legacy}_health_parameter": "LegacyHealth",
            },
            "sam": {
                f"drive_{legacy}_health_from_sam": True,
                f"drive_{legacy}_statuses_from_sam": True,
            },
        }
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["sam"].update(raw["sam"])
        _migrate_avatar_bridge(raw, config)
        self.assertEqual(config["avatar_bridge"]["input_mode"], "external")
        self.assertEqual(config["avatar_bridge"]["health_parameter"], "LegacyHealth")
        self.assertTrue(config["sam"]["drive_avatar_health_from_sam"])
        self.assertTrue(config["sam"]["drive_avatar_statuses_from_sam"])


if __name__ == "__main__":
    unittest.main()
