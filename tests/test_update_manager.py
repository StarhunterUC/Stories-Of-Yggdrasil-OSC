import unittest

from stories_yggdrasil_osc.update_manager import _select_release, _version_tuple


class UpdateVersionTests(unittest.TestCase):
    def test_semver_comparison(self):
        self.assertGreater(_version_tuple("0.7.1"), _version_tuple("0.7.0"))
        self.assertEqual(_version_tuple("v0.7.0"), _version_tuple("0.7.0"))

    def test_stable_beats_same_version_prebuild(self):
        self.assertLess(_version_tuple("0.8.21-prebuild.4"), _version_tuple("0.8.21"))

    def test_future_prebuild_beats_previous_stable(self):
        self.assertGreater(_version_tuple("0.8.22-prebuild.1"), _version_tuple("0.8.21"))

    def test_prebuild_revision_order(self):
        self.assertGreater(_version_tuple("0.8.22-prebuild.4"), _version_tuple("0.8.22-prebuild.3"))

    def test_stable_channel_ignores_prereleases(self):
        releases = [
            {"tag_name": "v0.8.21", "prerelease": False, "draft": False},
            {"tag_name": "v0.8.22-prebuild.1", "prerelease": True, "draft": False},
        ]
        selected = _select_release(releases, "stable")
        self.assertEqual(selected["tag_name"], "v0.8.21")

    def test_test_channel_accepts_newer_prerelease(self):
        releases = [
            {"tag_name": "v0.8.21", "prerelease": False, "draft": False},
            {"tag_name": "v0.8.22-prebuild.1", "prerelease": True, "draft": False},
        ]
        selected = _select_release(releases, "test")
        self.assertEqual(selected["tag_name"], "v0.8.22-prebuild.1")

    def test_test_channel_does_not_prefer_older_same_version_prebuild(self):
        releases = [
            {"tag_name": "v0.8.21", "prerelease": False, "draft": False},
            {"tag_name": "v0.8.21-prebuild.4", "prerelease": True, "draft": False},
        ]
        selected = _select_release(releases, "test")
        self.assertEqual(selected["tag_name"], "v0.8.21")


if __name__ == "__main__":
    unittest.main()
