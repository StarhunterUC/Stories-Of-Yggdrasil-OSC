import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stories_yggdrasil_osc import crash_reporting as cr


class CrashPrivacyTests(unittest.TestCase):
    def test_exception_details_never_include_secrets(self):
        try:
            raise RuntimeError("token secret john@example.com C:\\Users\\John\\file")
        except RuntimeError as exc:
            report = cr.make_report("desktop_exception", "0.8.22-prebuild.2",
                                    phase="running", exception=exc)
        content = str(report)
        self.assertNotIn("secret", content)
        self.assertNotIn("John", content)
        self.assertNotIn("@example.com", content)
        self.assertEqual(report["exception_type"], "RuntimeError")

    def test_local_queue_and_explicit_consent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cr, "_report_dir", return_value=Path(tmp)):
            path = cr.save_report(cr.make_report("installer_hang", "0.8.22-prebuild.2", phase="copy"))
            self.assertEqual(cr.load_report(path)["phase"], "copy")
            with self.assertRaises(PermissionError):
                cr.send_report(path, "https://admin.storiesofyggdrasil.com/api/osc/crash-report", consent=False)
            self.assertTrue(path.exists())
            with self.assertRaises(ValueError):
                cr.send_report(path, "https://attacker.example/api/osc/crash-report", consent=True)

    def test_unknown_data_not_retained(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cr, "_report_dir", return_value=Path(tmp)):
            data = cr.make_report("installer_error", "v0.8.22", phase="extract")
            data["discord_id"] = "123456789"
            data["error_message"] = "Private path"
            path = cr.save_report(data)
            self.assertNotIn("discord_id", path.read_text())
            self.assertNotIn("Private path", path.read_text())

    def test_stack_excludes_arbitrary_file_paths(self):
        report = cr.make_report("desktop_exception", "0.8.22", phase="running")
        self.assertNotIn("stack", report)


if __name__ == "__main__":
    unittest.main()
