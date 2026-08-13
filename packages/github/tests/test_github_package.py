"""Tests for the @fradser/github pi package.

Covers the native /github command menu (no skill surface — same pattern as
@fradser/memory) and guards the regression that removed the Claude Code Stop-hook
closeout mechanism (hooks/closeout-stop.sh, arm-closeout.sh,
clear-closeout.sh) in favor of asking the user directly in the conversation.
"""
from __future__ import annotations

import json
import os
import unittest

GH_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestGithubPackageManifest(unittest.TestCase):
    def test_package_json_validity(self):
        """package.json is a valid Pi package manifest — extensions only, no skills."""
        with open(os.path.join(GH_PKG_DIR, "package.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "@fradser/github")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertIn("pi", data)
        self.assertNotIn("skills", data["pi"], "github uses the /github menu, not skills")
        self.assertIn("extensions", data["pi"])
        self.assertIn("procedures", data.get("files", []))
        self.assertIn("references", data.get("files", []))
        self.assertIn("scripts", data.get("files", []))
        self.assertIn("@earendil-works/pi-coding-agent", data.get("peerDependencies", {}))


class TestGithubMenu(unittest.TestCase):
    def test_skills_directory_removed(self):
        """The skill surface is gone — workflows live in procedures/ behind the /github menu."""
        self.assertFalse(os.path.exists(os.path.join(GH_PKG_DIR, "skills")), "skills/ must be removed")

    def test_menu_extension_registers_command(self):
        """extensions/menu.ts registers the /github command with a select menu."""
        ext_path = os.path.join(GH_PKG_DIR, "extensions", "menu.ts")
        self.assertTrue(os.path.exists(ext_path), "extensions/menu.ts is missing")
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('registerCommand("github"', content)
        self.assertIn("ctx.ui.select", content)
        self.assertIn("sendUserMessage", content)
        self.assertIn("deliverAs", content)
        self.assertIn("{{PKG_DIR}}", content)
        self.assertIn("before_agent_start", content)

    def test_menu_covers_all_procedures(self):
        """Every menu item has a matching procedure file under procedures/."""
        ext_path = os.path.join(GH_PKG_DIR, "extensions", "menu.ts")
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        proc_dir = os.path.join(GH_PKG_DIR, "procedures")
        for name in ("create-issues.md", "create-pr.md", "resolve-issues.md", "review-pr.md"):
            self.assertIn(name, content, f"menu must reference {name}")
            self.assertTrue(os.path.exists(os.path.join(proc_dir, name)), f"{name} missing")

    def test_procedures_use_pkg_dir_placeholder(self):
        """Procedures resolve reference paths through the {{PKG_DIR}} placeholder."""
        for name in ("create-issues.md", "create-pr.md", "resolve-issues.md", "review-pr.md"):
            with open(os.path.join(GH_PKG_DIR, "procedures", name), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("{{PKG_DIR}}", content, f"{name} must use {{{{PKG_DIR}}}}")

    def test_no_skill_invocations_in_procedures(self):
        """Procedures never invoke themselves as /skill:... — the menu delivers them inline."""
        for name in ("create-issues.md", "create-pr.md", "resolve-issues.md", "review-pr.md"):
            with open(os.path.join(GH_PKG_DIR, "procedures", name), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("/skill:", content, f"{name} must not reference /skill:")

    def test_shared_reference_symlinks_resolve(self):
        """Per-workflow symlinks to references/shared/ must resolve to real files."""
        for root, _, files in os.walk(os.path.join(GH_PKG_DIR, "references")):
            for file in files:
                filepath = os.path.join(root, file)
                if os.path.islink(filepath):
                    self.assertTrue(
                        os.path.exists(filepath),
                        f"broken symlink: {filepath}",
                    )


class TestRiskyGate(unittest.TestCase):
    """extensions/risky-gate.ts forces pi's native confirm dialog on risky commands."""

    def setUp(self):
        with open(os.path.join(GH_PKG_DIR, "extensions", "risky-gate.ts"), "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_gate_extension_exists(self):
        """risky-gate.ts ships and registers a tool_call hook, not a tool."""
        self.assertIn('pi.on("tool_call"', self.content)
        self.assertNotIn("registerTool", self.content, "the gate is a hook, not a model tool")

    def test_merge_is_gated(self):
        """gh pr merge must trigger the native confirm dialog."""
        self.assertIn(r"gh\s+pr\s+merge", self.content)

    def test_force_worktree_remove_is_gated(self):
        """git worktree remove --force must be gated (discards changes)."""
        self.assertIn(r"worktree\s+remove", self.content)
        self.assertIn("--force", self.content)

    def test_uses_native_select_dialog(self):
        """The gate pops pi's option-select dialog and blocks on cancel."""
        self.assertIn("ctx.ui.select", self.content)
        self.assertIn("block: true", self.content)
        self.assertIn("event.input.command", self.content)  # command is rewritten per the chosen option

    def test_options_generated_by_model(self):
        """The options (and each option's command) are generated by the active model."""
        self.assertIn("ctx.model", self.content)
        self.assertIn("modelRegistry.complete", self.content)
        self.assertIn("Propose the alternative actions", self.content)
        self.assertIn("|||", self.content)  # label ||| command format

    def test_headless_block_instructs_conversation_ask(self):
        """Without UI the call is blocked with a conversation-ask reason."""
        self.assertIn("ctx.hasUI", self.content)
        self.assertIn("ask the user in the conversation", self.content)


class TestNoClaudeHooksRegression(unittest.TestCase):
    """The Stop-hook closeout mechanism was removed; nothing may reference it."""

    FORBIDDEN = (
        "closeout-stop",
        "arm-closeout",
        "clear-closeout",
        "review-pr-closeout.json",
        "Stop hook",
    )

    def test_no_hooks_directory(self):
        self.assertFalse(
            os.path.exists(os.path.join(GH_PKG_DIR, "hooks")),
            "hooks/ dir must be removed — pi packages cannot register Claude Code hooks",
        )

    def test_no_closeout_mechanism_references(self):
        for root, _, files in os.walk(GH_PKG_DIR):
            if "__pycache__" in root or "node_modules" in root or "tests" in root:
                continue
            for file in files:
                if not file.endswith((".md", ".sh", ".json", ".ts")):
                    continue
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for token in self.FORBIDDEN:
                    self.assertNotIn(token, content, f"Forbidden reference '{token}' in {filepath}")

    def test_workflows_ask_in_conversation(self):
        """Merge/confirm decision points instruct asking the user in the conversation."""
        review_pr = os.path.join(GH_PKG_DIR, "procedures", "review-pr.md")
        with open(review_pr, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Ask the user directly in the conversation", content)
        closeout = os.path.join(GH_PKG_DIR, "references", "review-pr", "closeout.md")
        with open(closeout, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Ask the", content)
        self.assertIn("user in the conversation", content)
        # No custom interaction tools may exist.
        for name in ("gh_ask_merge", "gh_confirm"):
            self.assertNotIn(name, content, f"{name} must be removed from closeout.md")


if __name__ == "__main__":
    unittest.main()
