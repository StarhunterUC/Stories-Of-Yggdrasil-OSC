import unittest
from stories_yggdrasil_osc.qol import ACTIVITY_TAG_COLORS, activity_color_tag


class ActivityColorTests(unittest.TestCase):
    def test_fixed_palette_and_categories(self):
        self.assertEqual(set(ACTIVITY_TAG_COLORS),
                         {"danger", "hold", "damage", "healing", "info", "neutral"})
        self.assertEqual(activity_color_tag("SAM ERROR", "endpoint unavailable"), "danger")
        self.assertEqual(activity_color_tag("COMBAT HOLD", "ambiguous"), "hold")
        self.assertEqual(activity_color_tag("WARNING", "Spell 146 unavailable"), "hold")
        self.assertEqual(activity_color_tag("COMBAT", "Aurora struck Alice for 1 damage."), "damage")
        self.assertEqual(activity_color_tag("RECOVERY", "Potion applied"), "healing")
        self.assertEqual(activity_color_tag("SAM LINK", "Connected"), "info")
        self.assertEqual(activity_color_tag("EVENT", "test"), "neutral")

    def test_user_text_cannot_be_a_tk_style(self):
        for value in ("", "DROP TABLE", "#000000", "name; style=ERROR"):
            self.assertIn(activity_color_tag(value), ACTIVITY_TAG_COLORS)


if __name__ == "__main__":
    unittest.main()
