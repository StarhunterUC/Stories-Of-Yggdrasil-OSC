import unittest

from stories_yggdrasil_osc.telemetry import coerce_percent, diablos_warning_label, percent_to_avatar_float


class DiablosDisplayTests(unittest.TestCase):
    def test_normalizes_percent_for_avatar(self):
        self.assertEqual(percent_to_avatar_float(25), 0.25)
        self.assertEqual(percent_to_avatar_float(100), 1.0)
        self.assertEqual(percent_to_avatar_float(-5), 0.0)

    def test_invalid_values_are_safe(self):
        self.assertEqual(coerce_percent(float("nan")), 0.0)
        self.assertEqual(coerce_percent(float("inf")), 0.0)

    def test_warning_thresholds(self):
        self.assertEqual(diablos_warning_label(24), "Stable")
        self.assertEqual(diablos_warning_label(25), "Warning")
        self.assertEqual(diablos_warning_label(50), "High warning")
        self.assertEqual(diablos_warning_label(90), "Severe warning")
        self.assertEqual(diablos_warning_label(98), "CRITICAL — Possession imminent")


if __name__ == "__main__":
    unittest.main()
