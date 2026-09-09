import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("review_pack", Path(__file__).parents[1] / "review_pack.py")
rp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rp)


class ReviewPackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo with spaces"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / "app.txt").write_text("before\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.store = rp.store_for(self.repo, self.base / "state")
        self.brief = self.base / "brief.md"
        self.brief.write_text("Change app.txt; verify the public behavior.\n")
        self.folder = rp.begin(self.repo, self.store, self.brief)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True).stdout

    def check(self, source, timeout=5):
        return rp.run_check(self.repo, self.store, [sys.executable, "-c", source], timeout)

    def packet(self):
        return json.loads((rp.report(self.repo, self.store) / "packet.json").read_text())

    def test_success_then_untracked_change_is_stale(self):
        r = self.check("print('completed')")
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(self.packet()["receipts"][0]["freshness"], "same-snapshot")
        (self.repo / "new file.txt").write_text("new")
        self.assertEqual(self.packet()["receipts"][0]["freshness"], "stale")

    def test_nonzero_is_not_success_even_on_same_snapshot(self):
        r = self.check("raise SystemExit(7)")
        self.assertEqual(r["exit_code"], 7)
        self.assertEqual(rp.freshness(r, rp.snapshot(self.repo)), "same-snapshot")

    def test_mutating_check_has_no_fresh_claim(self):
        r = self.check("from pathlib import Path; Path('app.txt').write_text('changed')")
        self.assertEqual(rp.freshness(r, rp.snapshot(self.repo)), "changed-during-check")

    def test_index_mode_and_head_changes_invalidate(self):
        a = rp.snapshot(self.repo)
        os.chmod(self.repo / "app.txt", 0o755)
        self.assertNotEqual(a, rp.snapshot(self.repo))
        self.git("add", ".")
        b = rp.snapshot(self.repo)
        self.git("commit", "-qm", "mode")
        self.assertNotEqual(b, rp.snapshot(self.repo))

    def test_receipts_do_not_leak_into_next_task(self):
        self.check("print('old task')")
        next_folder = rp.begin(self.repo, self.store, self.brief)
        self.assertNotEqual(next_folder, self.folder)
        self.assertEqual(self.packet()["receipts"], [])
        self.assertEqual(len(list(self.folder.glob("*.receipt.json"))), 1)

    def test_timeout_and_missing_binary_are_not_success(self):
        r = self.check("import time; time.sleep(5)", 0.15)
        self.assertEqual(r["outcome"], "timeout")
        r = rp.run_check(self.repo, self.store, ["/no/such/executable"], 1)
        self.assertEqual(r["outcome"], "launch_error")

    def test_deleted_or_modified_log_loses_evidence(self):
        r = self.check("print('check')")
        (self.folder / r["log"]).write_text("tampered")
        self.assertEqual(self.packet()["receipts"][0]["freshness"], "evidence-missing-or-modified")
        (self.folder / r["log"]).unlink()
        self.assertEqual(self.packet()["receipts"][0]["freshness"], "evidence-missing-or-modified")

    def test_log_is_bounded_and_marked(self):
        with patch.object(rp, "LOG_LIMIT", 64):
            r = self.check("print('x'*10000)")
        self.assertTrue(r["log_truncated"])
        self.assertEqual((self.folder / r["log"]).stat().st_size, 64)

    def test_export_includes_staged_and_unstaged_and_does_not_modify_repo(self):
        (self.repo / "app.txt").write_text("staged\n")
        self.git("add", ".")
        (self.repo / "app.txt").write_text("unstaged\n")
        (self.repo / "untracked.txt").write_text("new")
        before = rp.snapshot(self.repo)
        packet = rp.report(self.repo, self.store)
        self.assertIn("+unstaged", (packet / "diff.patch").read_text())
        report = (packet / "review.md").read_text()
        self.assertIn("untracked.txt", report)
        self.assertIn("NOT PROVIDED", report)
        self.assertEqual(before, rp.snapshot(self.repo))

    def test_parallel_begin_refused(self):
        with rp.lock(self.store):
            with self.assertRaisesRegex(ValueError, "Another"):
                rp.begin(self.repo, self.store, self.brief)

    def test_state_inside_repo_refused_and_submodule_refused(self):
        with self.assertRaises(ValueError):
            rp.store_for(self.repo, self.repo / "state")
        head = self.git("rev-parse", "HEAD").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{head},module")
        with self.assertRaisesRegex(ValueError, "Submodules"):
            rp.snapshot(self.repo)

    def test_symlink_target_and_deleted_files_change_digest(self):
        p = self.repo / "link"
        p.symlink_to("app.txt")
        a = rp.snapshot(self.repo)
        p.unlink(); p.symlink_to("missing")
        self.assertNotEqual(a, rp.snapshot(self.repo))
        a = rp.snapshot(self.repo)
        (self.repo / "app.txt").unlink()
        self.assertNotEqual(a, rp.snapshot(self.repo))

    def test_control_sequences_and_markdown_fences(self):
        self.assertNotIn("\x1b", rp.safe_text("\x1b[31mred"))
        self.assertTrue(rp.fenced("```hello").startswith("````\n"))

    def test_open_uses_invocation_live_cwd_not_plugin_cwd(self):
        listing = subprocess.CompletedProcess([], 0, json.dumps({"result": {"panes": [{
            "pane_id": "w1:p2", "foreground_cwd": str(self.repo)}]}}), "")
        with patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_BIN_PATH": "herdr-test",
                                    "HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"focused_pane_id": "w1:p2", "focused_pane_cwd": "/stale"})}):
            real_run = subprocess.run
            calls = []
            def fake_run(argv, **kw):
                if argv[0] == "herdr-test":
                    calls.append(argv)
                    return listing if argv[1] == "pane" else subprocess.CompletedProcess(argv, 0)
                return real_run(argv, **kw)
            with patch.object(rp.subprocess, "run", side_effect=fake_run):
                rp.open_panel()
        self.assertEqual(calls[-1][-2:], ["--cwd", str(self.repo.resolve())])


if __name__ == "__main__":
    unittest.main()
