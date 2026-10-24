import inspect
import unittest

from stories_yggdrasil_osc.update_manager import UpdateManager


class InstallerHangRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = inspect.getsource(UpdateManager._install_worker)

    def test_job_handoff_replaced(self):
        self.assertIn('Start-Process -FilePath "powershell.exe"', self.source)
        self.assertNotIn('Receive-Job $work', self.source)
        self.assertNotIn('Remove-Job $work', self.source)

    def test_stale_files_reset(self):
        self.assertIn('Remove-Item -LiteralPath $phasePath, $workerResult, $resultPath', self.source)
        self.assertIn('[System.IO.File]::WriteAllText($phasePath, $statusJson', self.source)
        self.assertNotIn('Move-Item -LiteralPath $tempFile -Destination $phasePath -Force', self.source)

    def test_worker_completion_checked(self):
        self.assertIn('if ($worker.HasExited) { break }', self.source)
        self.assertIn('$worker.ExitCode -ne 0', self.source)
        self.assertIn('$worker.Kill()', self.source)

    def test_parent_verifies_version_before_launch(self):
        self.assertLess(self.source.index('$installedVersion -ne $expectedVersion'),
                        self.source.index('Start-Process -FilePath $installedExe'))
        self.assertLess(self.source.index('Start-Process -FilePath $installedExe'),
                        self.source.index('Write-UpdateLog "Install succeeded.'))

    def test_no_blocking_staging_cleanup_in_finally(self):
        self.assertNotIn('Remove-Item $staging -Recurse', self.source)


if __name__ == '__main__':
    unittest.main()
