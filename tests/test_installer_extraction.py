import inspect
import unittest
from stories_yggdrasil_osc.update_manager import UpdateManager

class ExtractorRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = inspect.getsource(UpdateManager._install_worker)

    def test_streamed_zip_not_expand_archive(self):
        self.assertIn('[System.IO.Compression.ZipFile]::OpenRead($archive)', self.code)
        self.assertNotIn('Expand-Archive -LiteralPath $archive', self.code)
        self.assertIn('while (($bytesRead = $inputStream.Read(', self.code)

    def test_archive_path_limits_and_heartbeat(self):
        for fragment in ('StartsWith($root', 'unsupported symbolic link',
                         'Release exceeds unpacked size limit', 'file_index = $fileIndex',
                         'file $fileIndex of $fileTotal', 'lastCheckpointUtc'):
            self.assertIn(fragment, self.code)

    def test_single_session_and_distinct_staging(self):
        self.assertIn('StoriesOSC_Updater', self.code)
        self.assertIn('WaitOne(0)', self.code)
        self.assertIn('[guid]::NewGuid().ToString("N")', self.code)

    def test_phase_error_is_preserved(self):
        self.assertIn('$safePhase = if ($phaseName -in', self.code)

if __name__ == "__main__":
    unittest.main()
