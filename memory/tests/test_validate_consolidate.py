"""Tests for scripts/validate-consolidate.py — should-pass and should-fail.

A guard's worst failure mode is staying green while broken. Every deny path
asserts a non-zero exit and a distinctive error substring.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "scripts" / "validate-consolidate.py"


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ClusterCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inv = write(self.root / "inventory.txt", "project_a.md\nproject_b.md\n")
        self.cluster_ok = write(
            self.root / "cluster_ok.txt",
            "cluster: deploy\n  - project_a.md\n  - project_b.md\n",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cluster_covers_all_passes(self) -> None:
        r = run(
            [
                "--inventory",
                str(self.inv),
                "--cluster",
                str(self.cluster_ok),
                "--check=cluster",
            ]
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PASSED", r.stdout)

    def test_cluster_missing_file_fails(self) -> None:
        cluster = write(
            self.root / "cluster_miss.txt",
            "cluster: deploy\n  - project_a.md\n",
        )
        r = run(
            ["--inventory", str(self.inv), "--cluster", str(cluster), "--check=cluster"]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing from cluster", r.stderr)

    def test_cluster_duplicate_fails(self) -> None:
        inv = write(self.root / "inv1.txt", "project_a.md\n")
        cluster = write(
            self.root / "cluster_dup.txt",
            "cluster: a\n  - project_a.md\ncluster: b\n  - project_a.md\n",
        )
        r = run(["--inventory", str(inv), "--cluster", str(cluster), "--check=cluster"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate", r.stderr)

    def test_cluster_unknown_file_fails(self) -> None:
        inv = write(self.root / "inv2.txt", "project_a.md\n")
        cluster = write(
            self.root / "cluster_orphan.txt",
            "cluster: a\n  - project_a.md\n  - orphan.md\n",
        )
        r = run(["--inventory", str(inv), "--cluster", str(cluster), "--check=cluster"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("not in inventory", r.stderr)


class StalenessCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inv = write(
            self.root / "inventory.txt", "project_a.md\nfeedback_b.md\n"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_staleness_complete_passes(self) -> None:
        st = write(
            self.root / "st.txt",
            "project_a.md KEEP\nfeedback_b.md SUPERSEDED\n",
        )
        r = run(
            [
                "--inventory",
                str(self.inv),
                "--staleness",
                str(st),
                "--check=staleness",
            ]
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_staleness_missing_fails(self) -> None:
        st = write(self.root / "st_miss.txt", "project_a.md KEEP\n")
        r = run(
            [
                "--inventory",
                str(self.inv),
                "--staleness",
                str(st),
                "--check=staleness",
            ]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing from staleness", r.stderr)

    def test_staleness_invalid_verdict_fails(self) -> None:
        inv = write(self.root / "inv.txt", "project_a.md\n")
        st = write(self.root / "st_bad.txt", "project_a.md MAYBE\n")
        r = run(
            ["--inventory", str(inv), "--staleness", str(st), "--check=staleness"]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid verdict", r.stderr)

    def test_ops_only_underscore_normalized(self) -> None:
        inv = write(self.root / "inv_ops.txt", "project_a.md\n")
        st = write(self.root / "st_ops.txt", "project_a.md OPS_ONLY\n")
        r = run(
            ["--inventory", str(inv), "--staleness", str(st), "--check=staleness"]
        )
        self.assertEqual(r.returncode, 0, r.stderr)


class ReportGroundTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_path_arrow_passes_for_project(self) -> None:
        inv = write(self.root / "inv.txt", "project_deploy.md\n")
        report = write(
            self.root / "report.md",
            "## Consolidate report\n- Ground truth:\n  src/deploy.ts → found\n",
        )
        r = run(
            ["--inventory", str(inv), "--report", str(report), "--check=report"]
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ascii_arrow_passes(self) -> None:
        inv = write(self.root / "inv.txt", "project_deploy.md\n")
        report = write(
            self.root / "report.md",
            "src/deploy.ts -> missing\n",
        )
        r = run(
            ["--inventory", str(inv), "--report", str(report), "--check=report"]
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_path_fails_when_project_present(self) -> None:
        inv = write(self.root / "inv.txt", "project_deploy.md\n")
        report = write(
            self.root / "report.md",
            "## Consolidate report\n- Ground truth: looked fine\n",
        )
        r = run(
            ["--inventory", str(inv), "--report", str(report), "--check=report"]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("path", r.stderr.lower())

    def test_na_no_repo_passes(self) -> None:
        inv = write(self.root / "inv.txt", "project_deploy.md\n")
        report = write(
            self.root / "report.md",
            "Ground truth: N/A (no repo)\n",
        )
        r = run(
            ["--inventory", str(inv), "--report", str(report), "--check=report"]
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_feedback_only_without_path_passes(self) -> None:
        inv = write(self.root / "inv.txt", "feedback_pref.md\n")
        report = write(self.root / "report.md", "## Consolidate report\nok\n")
        r = run(
            ["--inventory", str(inv), "--report", str(report), "--check=report"]
        )
        self.assertEqual(r.returncode, 0, r.stderr)


class PrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.harness = self.root / "harness"
        self.public = self.root / "public"
        self.harness.mkdir()
        self.public.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_leaked_private_file_fails(self) -> None:
        write(
            self.harness / "MEMORY.md",
            "- [feedback_pref.md](feedback_pref.md) — prefs (harness only)\n"
            "- [project_x.md](project_x.md) — safe\n",
        )
        write(self.harness / "feedback_pref.md", "private\n")
        write(self.harness / "project_x.md", "safe\n")
        write(self.public / "MEMORY.md", "- [project_x.md](project_x.md) — safe\n")
        write(self.public / "project_x.md", "safe\n")
        write(self.public / "feedback_pref.md", "LEAK\n")
        r = run(
            [
                "--harness",
                str(self.harness),
                "--public",
                str(self.public),
                "--check=privacy",
            ]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("harness-only", r.stderr.lower())

    def test_public_index_harness_only_line_fails(self) -> None:
        write(
            self.harness / "MEMORY.md",
            "- [feedback_pref.md](feedback_pref.md) — prefs (harness only)\n",
        )
        write(self.harness / "feedback_pref.md", "private\n")
        write(
            self.public / "MEMORY.md",
            "- [feedback_pref.md](feedback_pref.md) — prefs (harness only)\n",
        )
        r = run(
            [
                "--harness",
                str(self.harness),
                "--public",
                str(self.public),
                "--check=privacy",
            ]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("harness only", r.stderr.lower())

    def test_clean_privacy_passes(self) -> None:
        write(
            self.harness / "MEMORY.md",
            "- [feedback_pref.md](feedback_pref.md) — prefs (harness only)\n"
            "- [project_x.md](project_x.md) — safe\n",
        )
        write(self.harness / "feedback_pref.md", "private\n")
        write(self.harness / "project_x.md", "safe\n")
        write(self.public / "MEMORY.md", "- [project_x.md](project_x.md) — safe\n")
        write(self.public / "project_x.md", "safe\n")
        r = run(
            [
                "--harness",
                str(self.harness),
                "--public",
                str(self.public),
                "--check=privacy",
            ]
        )
        self.assertEqual(r.returncode, 0, r.stderr)


class FullGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.harness = self.root / "harness"
        self.public = self.root / "public"
        self.harness.mkdir()
        self.public.mkdir()
        self.inv = write(
            self.root / "inventory.txt", "project_a.md\nfeedback_b.md\n"
        )
        self.cluster = write(
            self.root / "cluster.txt",
            "cluster: a\n  - project_a.md\ncluster: b\n  - feedback_b.md\n",
        )
        self.staleness = write(
            self.root / "staleness.txt",
            "project_a.md KEEP\nfeedback_b.md KEEP\n",
        )
        self.report = write(
            self.root / "report.md",
            "## Consolidate report\nsrc/a.ts → found\n",
        )
        write(
            self.harness / "MEMORY.md",
            "- [feedback_b.md](feedback_b.md) — x (harness only)\n"
            "- [project_a.md](project_a.md) — y\n",
        )
        write(self.harness / "feedback_b.md", "p\n")
        write(self.harness / "project_a.md", "s\n")
        write(self.public / "MEMORY.md", "- [project_a.md](project_a.md) — y\n")
        write(self.public / "project_a.md", "s\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_full_passes(self) -> None:
        r = run(
            [
                "--inventory",
                str(self.inv),
                "--cluster",
                str(self.cluster),
                "--staleness",
                str(self.staleness),
                "--report",
                str(self.report),
                "--harness",
                str(self.harness),
                "--public",
                str(self.public),
            ]
        )
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_full_fails_closed_on_cluster(self) -> None:
        bad_cluster = write(
            self.root / "bad_cluster.txt",
            "cluster: a\n  - project_a.md\n",
        )
        r = run(
            [
                "--inventory",
                str(self.inv),
                "--cluster",
                str(bad_cluster),
                "--staleness",
                str(self.staleness),
                "--report",
                str(self.report),
                "--harness",
                str(self.harness),
                "--public",
                str(self.public),
            ]
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing from cluster", r.stderr)


if __name__ == "__main__":
    unittest.main()
