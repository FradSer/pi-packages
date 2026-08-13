import json
import os
import unittest

MEMORY_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestInjectMemoryExtension(unittest.TestCase):
    def test_extension_file_exists(self):
        """Verify extensions/inject-memory.ts exists and has correct exports."""
        ext_path = os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts")
        self.assertTrue(os.path.exists(ext_path))
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("loadAndDeduplicateMemories", content)
        self.assertIn("formatMemoriesBlock", content)
        self.assertIn("before_agent_start", content)
        self.assertIn("registerCommand(\"memory\"", content)

    def test_consolidate_procedure_is_inline_not_a_skill(self):
        """Consolidate runs via procedures/consolidate.md, not via a skill doc path lookup."""
        ext_path = os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts")
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
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
        self.assertIn("./extensions", data["pi"]["extensions"])


class TestAutoConsolidation(unittest.TestCase):
    """Auto-consolidation triggers the inline consolidate procedure at a context
    fill fraction (features/auto-consolidate.feature)."""

    def ext_source(self) -> str:
        with open(os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts"), "r", encoding="utf-8") as f:
            return f.read()

    def test_hooks_user_input_and_agent_settled(self):
        """The extension must gate on user-typed turns (input source interactive)
        and evaluate at agent settle, so extension-injected runs never re-trigger."""
        content = self.ext_source()
        self.assertIn('pi.on("input"', content)
        self.assertIn('event.source', content)
        self.assertIn('"interactive"', content)
        self.assertIn('pi.on("agent_settled"', content)

    def test_reads_context_usage(self):
        """The trigger reads pi's native context usage (percent + window)."""
        content = self.ext_source()
        self.assertIn("getContextUsage", content)
        self.assertIn("usage.percent", content)
        self.assertIn("contextWindow", content)

    def test_fraction_setting_defaults_to_0_4(self):
        """consolidateAtContextFraction defaults to 0.4 (40% of the window) and is
        persisted in settings.json."""
        content = self.ext_source()
        self.assertIn("consolidateAtContextFraction", content)
        self.assertIn("0.4", content)
        self.assertIn("settings.json", content)

    def test_triggers_async_consolidation(self):
        """Crossing the fraction boundary spawns a non-interactive child Pi process
        (--print --no-session) instead of blocking the session with a follow-up."""
        content = self.ext_source()
        self.assertIn("node:child_process", content)
        self.assertIn("spawn", content)
        self.assertIn('"--print"', content)
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
        """The dreaming child's stdout is parsed for live progress events (tool_execution_start)
        and never read back into the session conversation. Only a transient status notify fires
        on completion."""
        content = self.ext_source()
        self.assertIn('stdio: ["ignore", "pipe", "pipe"]', content)
        self.assertIn('"Memory dreaming complete', content)
        self.assertIn("child.stdout", content)

    def test_single_flight(self):
        """Only one dreaming consolidation runs at a time — a running child blocks
        a second spawn even when a new fraction tier is crossed."""
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
        via an independent background child worker process."""
        content = self.ext_source()
        self.assertIn('choice.startsWith("Consolidate memory now")', content)
        self.assertIn("spawnAsyncConsolidation", content)
        self.assertNotIn("sendUserMessage", content)

    def test_dedicated_consolidate_command_is_sibling_of_memory(self):
        """A dedicated /consolidate command exists alongside /memory and triggers the
        same background worker without going through the management menu."""
        content = self.ext_source()
        self.assertIn('registerCommand("consolidate"', content)
        self.assertIn("spawnAsyncConsolidation", content)
        self.assertIn('"consolidate"', content)
        # The /memory menu itself must stay unchanged: only one registerCommand("memory")
        self.assertEqual(content.count('registerCommand("memory"'), 1)

    def test_tier_prevents_retrigger(self):
        """Tier-based firing (one trigger per fraction boundary) stops the
        consolidation run itself from re-triggering."""
        content = self.ext_source()
        self.assertIn("tier", content)
        self.assertIn("lastTriggeredTier", content)

    def test_gated_on_auto_memory_and_tui_mode(self):
        """Auto-consolidation only runs when auto-memory is on and the session is TUI."""
        content = self.ext_source()
        self.assertIn("autoMemory", content)
        self.assertIn('ctx.mode === "tui"', content)

    def test_fraction_zero_disables(self):
        """A fraction <= 0 disables auto-consolidation."""
        content = self.ext_source()
        self.assertIn("<= 0", content)
        self.assertIn("fraction", content)


if __name__ == "__main__":
    unittest.main()
