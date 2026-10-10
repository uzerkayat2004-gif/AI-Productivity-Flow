"""CI diagnostic regressions; no application imports or native resources."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "report_macos_launch_failure.py"
spec = importlib.util.spec_from_file_location("macos_launch_diagnostics", SCRIPT)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class LaunchDiagnosticsTests(unittest.TestCase):
    def test_disk_traceback_is_reported_and_credentials_are_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "crash_log.txt"
            log.write_text(
                'Traceback (most recent call last):\n'
                '  File "main.py", line 3509, in main\n'
                'ModuleNotFoundError: No module named _tkinter\n'
                'Authorization: Bearer sensitive-value\n'
                'api_key = sensitive-value\n'
                'SENTRY_DSN=https://sensitive-dsn@example.test/123\n'
                'Connection failed https://user:sensitive-password@example.test/path\n'
                'https://example.test/path?credential=sensitive-value\n',
                encoding="utf-8",
            )
            output = Path(folder) / "safe.log"
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--output", str(output), str(log)],
                text=True, capture_output=True, check=True,
            )
            self.assertIn("No module named _tkinter", result.stdout)
            self.assertNotIn("sensitive-value", result.stdout)
            self.assertNotIn("sensitive-dsn", result.stdout)
            self.assertNotIn("sensitive-password", result.stdout)
            self.assertEqual(result.stdout, output.read_text(encoding="utf-8"))

    def test_missing_empty_and_large_logs_are_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "startup.log"
            self.assertEqual(diagnostics.log_tail(log), "[log unavailable]")
            log.write_bytes(b"")
            self.assertEqual(diagnostics.log_tail(log), "[log empty]")
            log.write_bytes(b"sensitive-value" * 10000 + b"\n" + b"frame\n" * 130)
            tail = diagnostics.log_tail(log)
            self.assertEqual(len(tail.splitlines()), 120)
            self.assertNotIn("sensitive-value", tail)


if __name__ == "__main__":
    unittest.main()
