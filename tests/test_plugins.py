from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.plugins import discover_plugins, plugin_details, run_hook


PLUGIN = '''
PLUGIN = {
    "name": "test-plugin",
    "version": "1.2.3",
    "description": "A test plugin",
    "hooks": ["on_event", "on_match_finished"],
}


def on_event(context):
    return {"message": context.get("message")}


def on_match_finished(context):
    return {"match_id": context.get("match_id")}
'''


class PluginTests(unittest.TestCase):
    def test_discovery_and_metadata(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_plugin.py").write_text(PLUGIN, encoding="utf-8")
            found = discover_plugins(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].name, "test-plugin")
            self.assertEqual(plugin_details(root, "TEST-PLUGIN")["version"], "1.2.3")

    def test_hook_execution_isolated_and_returns_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_plugin.py").write_text(PLUGIN, encoding="utf-8")
            result = run_hook(root, "on_match_finished", {"match_id": 7})
            self.assertEqual(result[0]["result"]["match_id"], 7)

    def test_broken_plugin_is_skipped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.py").write_text("raise RuntimeError('boom')", encoding="utf-8")
            self.assertEqual(discover_plugins(root), [])


if __name__ == "__main__":
    unittest.main()
