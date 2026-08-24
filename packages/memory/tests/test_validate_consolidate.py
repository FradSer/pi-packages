"""Contract tests for the dependency-free consolidation artifact validator."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "scripts" / "validate-consolidate.py"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ValidatorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.harness = self.repo / "harness"
        self.public = self.repo / ".memory"
        self.harness.mkdir(parents=True)
        self.public.mkdir(parents=True)
        write(self.repo / "src" / "example.ts", "export const example = true;\n")
        self.run_id = "memory-run-1"
        self.scope_key = "c" * 64
        self.scope = "b" * 64
        self.artifact = "a" * 64

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def plan(self, names: list[str] | None = None) -> dict[str, object]:
        names = ["project_example.md", "feedback_preference.md"] if names is None else names
        return {
            "kind": "memory-consolidation-plan",
            "version": 1,
            "runId": self.run_id,
            "scopeKey": self.scope_key,
            "scopeDigest": self.scope,
            "snapshotDigest": self.artifact,
            "artifactHash": self.artifact,
            "selected": names,
            "inventory": [
                {
                    "name": name,
                    "classification": "private" if name.startswith("feedback_") else "safe",
                }
                for name in names
            ],
            "clusters": [{"name": "project", "files": names}] if names else [],
            "staleness": [{"name": name, "verdict": "KEEP"} for name in names],
            "grounding": [
                {
                    "name": name,
                    "status": "VERIFIED" if name.startswith("project_") else "N/A",
                    "reason": "no repository claim" if not name.startswith("project_") else "claim verified",
                    "observations": [{"path": "src/example.ts", "status": "found"}]
                    if name.startswith("project_")
                    else [],
                }
                for name in names
            ],
            "report": [{"name": name, "status": "KEEP", "summary": "durable"} for name in names],
        }

    def memory_layout(self, private: bool = True) -> None:
        harness_lines = [
            "- [project_example.md](project_example.md) — safe",
        ]
        if private:
            harness_lines.insert(
                0,
                "- [feedback_preference.md](feedback_preference.md) — private (harness only)",
            )
            write(self.harness / "feedback_preference.md", "private\n")
        write(self.harness / "project_example.md", "safe\n")
        write(self.harness / "MEMORY.md", "\n".join(harness_lines) + "\n")
        write(self.public / "project_example.md", "safe\n")
        write(self.public / "MEMORY.md", "- [project_example.md](project_example.md) — safe\n")

    def receipt(self, plan: dict[str, object]) -> dict[str, object]:
        plan_path = self.root / "plan.json"
        if not plan_path.exists():
            write_json(plan_path, plan)

        def hashes(root: Path) -> dict[str, str]:
            return {
                path.name: sha(path)
                for path in sorted(root.glob("*.md"), key=lambda item: item.name)
            }

        source_hashes = {"harness": hashes(self.harness), "public": hashes(self.public)}
        return {
            "kind": "memory-consolidation-receipt",
            "version": 1,
            "schemaVersion": 1,
            "phase": "post",
            "runId": plan["runId"],
            "scopeDigest": plan["scopeDigest"],
            "artifactHash": plan["artifactHash"],
            "planDigest": sha(self.root / "plan.json"),
            "selected": plan["inventory"],
            "sourceHashes": source_hashes,
            "finalHashes": {"harness": hashes(self.harness), "public": hashes(self.public)},
        }

    def invoke_plan(self, plan: dict[str, object], *extra: str) -> subprocess.CompletedProcess[str]:
        plan_path = write_json(self.root / "plan.json", plan)
        return run([
            "--plan", str(plan_path),
            "--check=plan",
            "--expected-scope-key", self.scope_key,
            "--expected-scope-digest", self.scope,
            "--expected-artifact-hash", self.artifact,
            *extra,
        ])

    def test_valid_plan_emits_structured_success(self) -> None:
        result = self.invoke_plan(self.plan())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["ok"])
        self.assertEqual(output["checks"], ["plan"])

    def test_empty_inventory_is_a_verified_noop(self) -> None:
        plan = self.plan([])
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["details"]["inventoryCount"], 0)

    def test_inventory_rejects_duplicate_and_path_names(self) -> None:
        plan = self.plan(["project_example.md", "nested/project_other.md"])
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("artifact_identity", result.stdout)

        plan = self.plan(["project_example.md", "project_example.md"])
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate", result.stdout)

    def test_memory_index_is_case_insensitive_and_excluded(self) -> None:
        plan = self.plan(["MEMORY.md", "project_example.md"])
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["details"]["inventoryCount"], 1)

    def test_legacy_underscore_verdict_is_rejected(self) -> None:
        plan = self.plan()
        plan["staleness"] = [{"name": name, "verdict": "OPS_ONLY"} for name in ["project_example.md", "feedback_preference.md"]]
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid verdict", result.stdout)

    def test_canonical_identity_fields_are_required_and_aliases_must_match(self) -> None:
        plan = self.plan()
        del plan["scopeDigest"]
        plan["scopeKey"] = self.scope_key
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing scopeDigest", result.stdout)

        plan = self.plan()
        plan["scopeKey"] = "d" * 64
        result = self.invoke_plan(plan, "--expected-scope-key", self.scope_key)
        self.assertEqual(result.returncode, 1)
        self.assertIn("scopeKey does not match parent expectation", result.stdout)

    def test_report_outcomes_must_be_non_empty_strings(self) -> None:
        plan = self.plan()
        plan["report"] = [{"name": name, "status": 0} for name in plan["inventory"]]
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be a string", result.stdout)

    def test_per_item_records_are_required(self) -> None:
        plan = self.plan()
        plan["report"] = [{"name": "project_example.md", "status": "KEEP"}]
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing per-item record", result.stdout)

    def test_grounding_paths_must_stay_inside_repo(self) -> None:
        plan = self.plan(["project_example.md"])
        plan["grounding"] = [
            {
                "name": "project_example.md",
                "status": "VERIFIED",
                "observations": [{"path": "../outside.txt", "status": "found"}],
            }
        ]
        result = self.invoke_plan(plan, "--repo-root", str(self.repo))
        self.assertEqual(result.returncode, 1)
        self.assertIn("containment", result.stdout)

    def test_cli_parse_errors_are_structured_json(self) -> None:
        result = run(["--unknown-option"])
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertFalse(output["ok"])
        self.assertEqual(output["errors"][0]["code"], "usage")

    def test_clean_privacy_split_passes(self) -> None:
        self.memory_layout()
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
        ])
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_privacy_rejects_same_canonical_roots(self) -> None:
        self.memory_layout()
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.harness / ".." / "harness"),
            "--check=privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("distinct canonical", result.stdout)

    def test_privacy_rejects_memory_file_count_before_reading(self) -> None:
        self.memory_layout(private=False)
        for index in range(6):
            write(self.harness / f"memory_{index}.md", "safe\n")
        write(self.harness / "MEMORY.md", "\n".join(
            [f"- [memory_{index}.md](memory_{index}.md) — safe" for index in range(6)]
        ) + "\n")
        # Default count bound is 4096 (aligned with the runtime); shrink it to exercise the guard.
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
            "--max-memory-files", "5",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("memory file count", result.stdout)

    def test_privacy_rejects_oversized_memory_file_before_reading(self) -> None:
        self.memory_layout(private=False)
        write(self.harness / "project_example.md", "x" * 64_001)
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("per-file", result.stdout)

    def test_privacy_rejects_oversized_memory_root_before_reading(self) -> None:
        self.memory_layout(private=False)
        write(self.harness / "project_example.md", "x" * 50_000)
        write(self.harness / "project_second.md", "x" * 50_000)
        write(self.harness / "MEMORY.md", "- [project_example.md](project_example.md)\n- [project_second.md](project_second.md)\n")
        # Default aggregate bound is file-count × per-file; shrink it to exercise the guard.
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
            "--max-total-bytes", "96000",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("aggregate", result.stdout)

    def test_safe_mirror_drift_fails_closed(self) -> None:
        self.memory_layout(private=False)
        write(self.public / "project_example.md", "changed\n")
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("safe mirror drift", result.stdout)

    def test_unindexed_public_file_fails(self) -> None:
        self.memory_layout(private=False)
        write(self.public / "orphan.md", "orphan\n")
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("orphan/unindexed", result.stdout)

    def test_symlinked_memory_child_fails(self) -> None:
        self.memory_layout(private=False)
        target = self.root / "target.md"
        write(target, "outside\n")
        os.symlink(target, self.public / "linked.md")
        result = run([
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("symlink", result.stdout)

    def test_receipt_binds_run_scope_hash_and_final_state(self) -> None:
        self.memory_layout()
        plan = self.plan()
        plan_path = write_json(self.root / "plan.json", plan)
        receipt_path = write_json(self.root / "post-receipt.json", self.receipt(plan))
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
            "--expected-run-id", self.run_id,
            "--expected-scope-key", self.scope_key,
            "--expected-scope-digest", self.scope,
            "--expected-artifact-hash", self.artifact,
        ])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["details"]["receiptVerified"])

    def test_plan_accepts_distinct_scope_key_and_digest(self) -> None:
        result = self.invoke_plan(self.plan())
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_plan_rejects_wrong_scope_key(self) -> None:
        plan = self.plan()
        plan["scopeKey"] = "d" * 64
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("scopeKey does not match parent expectation", result.stdout)

    def test_plan_selected_scope_must_match_parent_expectation(self) -> None:
        plan = self.plan()
        result = self.invoke_plan(plan, "--expected-selected", "project_example.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("selected scope does not match parent expectation", result.stdout)

    def test_grounding_found_path_must_exist(self) -> None:
        plan = self.plan(["project_example.md"])
        plan["grounding"] = [{
            "name": "project_example.md",
            "status": "VERIFIED",
            "observations": [{"path": "src/missing.ts", "status": "found"}],
        }]
        result = self.invoke_plan(plan, "--repo-root", str(self.repo))
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stdout)

    def test_operation_classification_must_match_inventory(self) -> None:
        plan = self.plan()
        plan["operations"] = [{
            "name": "project_example.md",
            "kind": "rewrite",
            "classification": "private",
            "content": "rewritten\n",
        }]
        result = self.invoke_plan(plan)
        self.assertEqual(result.returncode, 1)
        self.assertIn("classification does not match inventory", result.stdout)

    def test_receipt_path_must_match_post_phase(self) -> None:
        self.memory_layout()
        plan = self.plan()
        plan_path = write_json(self.root / "plan.json", plan)
        receipt_path = write_json(self.root / "receipt.json", self.receipt(plan))
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("path must be post-receipt.json", result.stdout)

    def test_receipt_path_must_match_plan_run_directory(self) -> None:
        self.memory_layout()
        plan = self.plan()
        plan_path = write_json(self.root / "plan.json", plan)
        other = self.root / "other"
        receipt_path = write_json(other / "post-receipt.json", self.receipt(plan))
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("exact plan run directory", result.stdout)

    def test_post_receipt_source_hashes_bind_to_parent_manifest(self) -> None:
        self.memory_layout()
        plan = self.plan()
        plan_path = write_json(self.root / "plan.json", plan)
        receipt = self.receipt(plan)
        write_json(self.root / "manifest.json", {"sourceHashes": receipt["sourceHashes"]})
        receipt["sourceHashes"]["harness"]["project_example.md"] = "0" * 64
        receipt_path = write_json(self.root / "post-receipt.json", receipt)
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("source hashes", result.stdout)

    def test_receipt_rejects_schema_valid_plan_substitution(self) -> None:
        self.memory_layout()
        plan = self.plan()
        plan_path = write_json(self.root / "plan.json", plan)
        receipt_path = write_json(self.root / "post-receipt.json", self.receipt(plan))
        substituted = self.plan()
        substituted["report"] = [{"name": item["name"], "status": "KEEP", "summary": "substituted"} for item in substituted["inventory"]]
        write_json(plan_path, substituted)
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("planDigest", result.stdout)

    def test_receipt_requires_phase(self) -> None:
        self.memory_layout()
        plan = self.plan()
        receipt = self.receipt(plan)
        del receipt["phase"]
        plan_path = write_json(self.root / "plan.json", plan)
        receipt_path = write_json(self.root / "post-receipt.json", receipt)
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("phase must be pre or post", result.stdout)

    def test_receipt_requires_canonical_identity_fields(self) -> None:
        self.memory_layout()
        plan = self.plan()
        receipt = self.receipt(plan)
        del receipt["scopeDigest"]
        receipt["scopeKey"] = self.scope
        plan_path = write_json(self.root / "plan.json", plan)
        receipt_path = write_json(self.root / "post-receipt.json", receipt)
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("receipt: missing scopeDigest", result.stdout)

    def test_foreign_receipt_is_rejected(self) -> None:
        self.memory_layout()
        plan = self.plan()
        receipt = self.receipt(plan)
        receipt["runId"] = "other-run"
        plan_path = write_json(self.root / "plan.json", plan)
        receipt_path = write_json(self.root / "post-receipt.json", receipt)
        result = run([
            "--plan", str(plan_path),
            "--receipt", str(receipt_path),
            "--harness", str(self.harness),
            "--public", str(self.public),
            "--check=plan,receipt,privacy",
        ])
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match plan", result.stdout)


if __name__ == "__main__":
    unittest.main()
