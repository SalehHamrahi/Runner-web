import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliSmokeTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        merged = os.environ.copy()
        merged.pop("RUNNER_VENV_ACTIVE", None)
        if env:
            merged.update(env)
        return subprocess.run(
            [sys.executable, str(ROOT / "runner.py"), *args],
            cwd=ROOT,
            env=merged,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Runner", result.stdout)

    def test_help(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Tournament management CLI", result.stdout)

    def test_notifications_command_on_temp_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runner.db"
            result = self.run_cli("notifications", "--limit", "1", env={"RUNNER_DB": str(db)})
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload, [])
