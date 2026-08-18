import json
import os
import subprocess
import unittest

MEMORY_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestInjectMemoryExtension(unittest.TestCase):
    def ext_source(self) -> str:
        with open(os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts"), "r", encoding="utf-8") as f:
            return f.read()

    def test_extension_file_exists(self):
        """Verify extensions/inject-memory.ts exists and has correct exports."""
        ext_path = os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts")
        self.assertTrue(os.path.exists(ext_path))
        content = self.ext_source()
        self.assertIn("loadAndDeduplicateMemories", content)
        self.assertIn("formatMemoriesBlock", content)
        self.assertIn("before_agent_start", content)
        self.assertIn('registerCommand("memory"', content)
        self.assertIn('registerCommand("consolidate"', content)

    def test_auto_memory_guidance_present_without_auto_consolidation_text(self):
        """Auto-memory guidance is injected for the LLM to actively capture durable facts,
        but it must NOT contain auto-consolidation threshold instructions."""
        content = self.ext_source()
        self.assertIn("AUTO_MEMORY_GUIDANCE", content)
        self.assertIn("autoMemory", content)
        self.assertIn("readSettings", content)
        self.assertIn("writeSettings", content)
        self.assertIn("settings.json", content)
        # Guidance should tell LLM to capture durable facts
        self.assertIn("You maintain a durable project memory", content)
        # Guidance must NOT reference automatic consolidation triggers or fractions
        self.assertNotIn("consolidateAtContextFraction", content)
        self.assertNotIn("consolidates memory automatically", content)
        self.assertNotIn("40%", content)

    def test_no_auto_consolidation_hooks(self):
        """Auto-consolidation hooks (agent_settled, input tracking, context fraction) are removed."""
        content = self.ext_source()
        self.assertNotIn('pi.on("agent_settled"', content)
        self.assertNotIn("getContextUsage", content)
        self.assertNotIn("consolidateAtContextFraction", content)
        self.assertNotIn("lastTriggeredTier", content)
        self.assertNotIn("userTurnSeen", content)

    def test_memory_model_configuration_is_available(self):
        content = self.ext_source()
        self.assertIn('"./config"', content)
        self.assertIn("availableMemoryModels", content)
        self.assertIn("chooseMemoryModel", content)
        self.assertIn("enterMemoryModel", content)
        self.assertIn("memoryConfigPath", content)
        self.assertIn('"--model"', content)
        with open(
            os.path.join(MEMORY_PKG_DIR, "extensions", "config.ts"),
            encoding="utf-8",
        ) as f:
            self.assertIn("PI_MEMORY_MODEL", f.read())

    def test_menu_options_contain_auto_memory_toggle(self):
        """The /memory menu provides auto-memory toggle and memory management."""
        content = self.ext_source()
        self.assertIn('"Consolidate memory now"', content)
        self.assertIn("Select memory model", content)
        self.assertIn("Enter provider/model manually", content)
        self.assertIn('"Edit user instructions (~/.pi/agent/AGENTS.md)"', content)
        self.assertIn('"Open memory folder"', content)
        self.assertIn("Toggle auto-memory", content)
        self.assertIn("Auto-memory: ${status}", content)

    def test_consolidate_procedure_is_inline_not_a_skill(self):
        """Consolidate runs via procedures/consolidate.md, not via a skill doc path lookup."""
        content = self.ext_source()
        self.assertNotIn("skills/consolidate", content)
        self.assertNotIn("SKILL.md", content)
        self.assertIn("procedures", content)
        self.assertIn("consolidate.md", content)

    def test_consolidate_procedure_doc_exists(self):
        """The inline procedure document ships under procedures/ with the
        validator path placeholder."""
        proc_path = os.path.join(MEMORY_PKG_DIR, "procedures", "consolidate.md")
        self.assertTrue(os.path.exists(proc_path))
        with open(proc_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("{{PKG_DIR}}", content)
        self.assertIn("staleness rubric", content.lower())
        self.assertIn("validate-consolidate.py", content)
        self.assertFalse(os.path.exists(os.path.join(MEMORY_PKG_DIR, "skills")))

    def test_package_json_manifest(self):
        """Verify package.json registers extensions."""
        manifest_path = os.path.join(MEMORY_PKG_DIR, "package.json")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("pi", data)
        self.assertIn("extensions", data["pi"])
        # The entry is the explicit factory file; config.ts is a helper module,
        # never a directory glob (pi would otherwise try to load config.ts as an extension).
        self.assertIn("./extensions/inject-memory.ts", data["pi"]["extensions"])


class TestManualConsolidation(unittest.TestCase):
    """Memory consolidation runs on-demand in the background
    (features/consolidate.feature)."""

    def ext_source(self) -> str:
        with open(os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts"), "r", encoding="utf-8") as f:
            return f.read()

    def test_triggers_async_consolidation(self):
        """Triggering consolidation starts a non-interactive background run
        (--print --mode json --no-session) instead of blocking the session."""
        content = self.ext_source()
        self.assertIn("node:child_process", content)
        self.assertIn("spawn", content)
        self.assertIn('"--print"', content)
        self.assertIn('"--mode"', content)
        self.assertIn('"json"', content)
        self.assertIn('"--no-session"', content)
        self.assertIn("consolidate.md", content)
        self.assertIn("{{PKG_DIR}}", content)

    def test_dreaming_widget_above_editor(self):
        """A "dreaming" widget is shown above the input editor while the child runs
        and cleared when it exits."""
        content = self.ext_source()
        self.assertIn("setWidget", content)
        self.assertIn("dreaming", content)
        self.assertIn('"memory-dreaming"', content)

    def test_result_never_returned_to_session(self):
        """The dreaming child's stdout is parsed for live progress events and never
        returned to the main session conversation."""
        content = self.ext_source()
        self.assertIn('stdio: ["ignore", "pipe", "pipe"]', content)
        self.assertIn("child.stdout", content)
        self.assertIn("tool_execution_start", content)

    def test_resolves_procedure_relative_to_extension_module(self):
        """An npm, git, or local install finds its shipped procedure from the
        extension module rather than Pi settings strings or the project cwd."""
        content = self.ext_source()
        self.assertIn('fileURLToPath(import.meta.url)', content)
        self.assertIn('path.resolve(extensionDir, "..")', content)
        self.assertNotIn('"settings.json"', content[content.index("function resolvePackageDir"):content.index("// ── background consolidation")])
        self.assertNotIn('process.cwd()', content[content.index("function resolvePackageDir"):content.index("// ── background consolidation")])

    def test_success_requires_tool_validator_and_gate_report_evidence(self):
        """A zero exit is not consolidation proof. Success requires completed tool
        work, a passing full validator, and the child report's G1–G8 evidence."""
        content = self.ext_source()
        self.assertIn("tool_execution_start", content)
        self.assertIn("tool_execution_end", content)
        self.assertIn("toolArgsByCallId", content)
        self.assertIn("validate-consolidate.py", content)
        self.assertIn("G1", content)
        self.assertIn("G8", content)
        self.assertIn('"cluster", "staleness", "report", "privacy"', content)
        self.assertIn("Memory dreaming complete — memory consolidated.", content)

    def test_zero_exit_without_evidence_is_diagnostic_not_success(self):
        """A provider failure can exit zero with no work. The completion branch
        must report missing proof and avoid the success wording."""
        content = self.ext_source()
        self.assertIn("Memory dreaming finished without verified consolidation", content)
        self.assertIn("missing", content)
        self.assertIn('`Memory dreaming finished without verified consolidation: missing ${missing.join(", ")}', content)

    def test_verified_jsonl_evidence_allows_success(self):
        """A real TypeScript harness verifies the JSONL correlation: validator
        args are recorded at start and recognized at tool completion."""
        harness = os.path.join(MEMORY_PKG_DIR, "tests", "consolidation_evidence_harness.ts")
        result = subprocess.run(
            ["bun", harness, "verified"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), [])

    def test_empty_jsonl_evidence_is_diagnostic(self):
        """A zero-exit child with no JSONL work yields every missing proof rather
        than allowing the success notification."""
        harness = os.path.join(MEMORY_PKG_DIR, "tests", "consolidation_evidence_harness.ts")
        result = subprocess.run(
            ["bun", harness, "empty"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(result.stdout),
            ["completed tool work", "a passing full validator", "a G1–G8 passed gate report"],
        )

    def test_single_flight(self):
        """Only one dreaming consolidation runs at a time — a running child blocks
        a second spawn."""
        content = self.ext_source()
        self.assertIn("dreaming", content)
        self.assertIn("active", content)

    def test_session_file_passed_to_child(self):
        """The child receives the current session file path for Step 0 capture,
        plus the project cwd and harness memory dir."""
        content = self.ext_source()
        self.assertIn("getSessionFile", content)
        self.assertIn("harness", content)

    def test_menu_triggers_async_consolidation(self):
        """The /memory menu item 'Consolidate memory now' triggers async consolidation
        via the background consolidation runner."""
        content = self.ext_source()
        self.assertIn('choice.startsWith("Consolidate memory now")', content)
        self.assertIn("spawnAsyncConsolidation", content)
        self.assertNotIn("sendUserMessage", content)

    def test_dedicated_consolidate_command_is_sibling_of_memory(self):
        """A dedicated /consolidate command exists alongside /memory and triggers the
        same background runner without going through the management menu."""
        content = self.ext_source()
        self.assertIn('registerCommand("consolidate"', content)
        self.assertIn("spawnAsyncConsolidation", content)
        self.assertIn('"consolidate"', content)
        # The /memory menu itself must stay unchanged: only one registerCommand("memory")
        self.assertEqual(content.count('registerCommand("memory"'), 1)


if __name__ == "__main__":
    unittest.main()
