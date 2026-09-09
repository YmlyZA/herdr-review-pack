import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

PLUGIN = Path(__file__).resolve().parents[1]


class CliTest(unittest.TestCase):
    def test_cli_and_panel_complete_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "checkout"
            repo.mkdir()
            def git(*args):
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (repo / "app").write_text("v1")
            git("add", ".")
            git("commit", "-qm", "base")
            brief = base / "task.md"
            brief.write_text("Implement v2 and verify it.")
            state = base / "state"
            cmd = [sys.executable, str(PLUGIN / "review_pack.py"), "--repo", str(repo), "--state-dir", str(state)]
            def run(*args):
                return subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=15)
            self.assertEqual(run("begin", "--brief", str(brief)).returncode, 0)
            (repo / "app").write_text("v2")
            checked = run("check", "--", sys.executable, "-c", "from pathlib import Path; assert Path('app').read_text() == 'v2'")
            self.assertEqual(checked.returncode, 0, checked.stderr)
            packed = run("pack")
            self.assertEqual(packed.returncode, 0, packed.stderr)
            packet = json.loads((Path(packed.stdout.strip()) / "packet.json").read_text())
            self.assertEqual(packet["receipts"][0]["freshness"], "same-snapshot")
            failed = run("check", "--", sys.executable, "-c", "raise SystemExit(6)")
            self.assertEqual(failed.returncode, 6)
            (repo / "app").write_text("v3")
            panel = subprocess.run(["sh", str(PLUGIN / "panel.sh")], cwd=repo,
                                   input="r\nd\nl\n1\nq\n", capture_output=True, text=True, timeout=15,
                                   env={**os.environ, "HERDR_PLUGIN_ROOT": str(PLUGIN), "REVIEW_PACK_STATE_DIR": str(state)})
            self.assertEqual(panel.returncode, 0, panel.stderr)
            self.assertIn("stale", panel.stdout)
            self.assertIn("+v3", panel.stdout)
            self.assertIn("Shared state directory", panel.stdout)

    def test_manifest_entrypoints_resolve(self):
        manifest = tomllib.loads((PLUGIN / "herdr-plugin.toml").read_text())
        self.assertEqual(manifest["id"], "herdr-review-pack")
        for item in manifest["actions"]:
            self.assertTrue((PLUGIN / item["command"][1]).is_file())
        for item in manifest["panes"]:
            # Pane commands run in the reviewed repo's cwd; they must locate the
            # script via HERDR_PLUGIN_ROOT rather than a relative path.
            self.assertEqual(item["command"][:2], ["sh", "-c"])
            self.assertIn("$HERDR_PLUGIN_ROOT/panel.sh", item["command"][2])
            self.assertTrue((PLUGIN / "panel.sh").is_file())
        self.assertNotIn("startup", manifest)
        self.assertNotIn("events", manifest)


if __name__ == "__main__":
    unittest.main()
