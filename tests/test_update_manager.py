import unittest
from stories_yggdrasil_osc.update_manager import _version_tuple


class UpdateVersionTests(unittest.TestCase):
    def test_semver_comparison(self):
        self.assertGreater(_version_tuple("0.7.1"), _version_tuple("0.7.0"))
        self.assertEqual(_version_tuple("v0.7.0"), _version_tuple("0.7.0"))


if __name__ == "__main__":
    unittest.main()
