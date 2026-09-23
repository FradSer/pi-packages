"""Offline end-to-end worktree reproduction through the installed Pi CLI."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class WorktreePrintTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pi"), "installed Pi CLI required")
    def test_print_host_resumes_edits_only_in_replacement_worktree(self) -> None:
        fixture = Path(__file__).with_name("worktree_print_fixture.ts").resolve()
        with tempfile.TemporaryDirectory(prefix="pi-worktree-print-") as temp:
            base = Path(temp).resolve()
            repo, agent = base / "repo", base / "agent"
            repo.mkdir()
            agent.mkdir()
            for args in (("init", "-q"), ("config", "user.name", "Test"),
                         ("config", "user.email", "test@example.invalid")):
                subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
            (repo / "tracked.txt").write_text("original\n")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
            env = {key: value for key, value in os.environ.items()
                   if not any(word in key for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
            env["PI_CODING_AGENT_DIR"] = str(agent)
            result = subprocess.run(
                ["pi", "--print", "--mode", "json", "-ne", "-ns", "-np", "-nc", "--no-themes",
                 "-e", str(fixture), "--model", "worktree-live/test", "Enter worktree and edit there"],
                cwd=repo, env=env, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = repo / ".pi" / "worktrees" / "live"
            self.assertTrue(target.exists(), result.stdout + result.stderr)
            self.assertEqual((repo / "tracked.txt").read_text(), "original\n")
            self.assertFalse((repo / "leaked.txt").exists())
            self.assertEqual((target / "tracked.txt").read_text(), "worktree\n")
            self.assertEqual((target / "new.txt").read_text(), "worktree only")
            self.assertEqual(Path((target / "actual-cwd.txt").read_text().strip()).resolve(), target.resolve())
            self.assertIn("WORKTREE_PRINT_OK", result.stdout)
