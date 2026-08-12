"""Tests for the @fradser/git-agent pi package.

Guards the regression that removed the Claude Code pre-tool hook sidecar
script (hooks/ directory) in favor of the native pi extension
(extensions/validate-commit.ts), which intercepts tool_call events in-process.
"""
from __future__ import annotations

import json
import os
import unittest

GA_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tokens that must never reappear outside tests. Built by concatenation so this
# file itself does not contain the forbidden literals.
HOOK_SCRIPT_NAME = "validate-commit-" + "pretool"
HOOK_EVENT = "Pre" + "ToolUse"


class TestGitAgentManifest(unittest.TestCase):
    def test_package_json_validity(self):
        """package.json is a valid Pi package manifest with skills + extensions."""
        with open(os.path.join(GA_PKG_DIR, "package.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "@fradser/git-agent")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertIn("skills", data["pi"])
        self.assertIn("extensions", data["pi"])
        self.assertIn("@earendil-works/pi-coding-agent", data.get("peerDependencies", {}))
        self.assertNotIn("hooks", data.get("files", []))
        self.assertNotIn("pretool-hook", data.get("keywords", []))


class TestNoClaudeHookRegression(unittest.TestCase):
    def test_hooks_directory_removed(self):
        """The Claude Code pre-tool hook sidecar must be gone."""
        self.assertFalse(
            os.path.exists(os.path.join(GA_PKG_DIR, "hooks")),
            "hooks/ must be removed — pi has no hook system; the extension covers the guard",
        )

    def test_no_pretool_references(self):
        """Nothing outside tests may reference the removed hook."""
        forbidden = (HOOK_SCRIPT_NAME, HOOK_EVENT)
        for root, _, files in os.walk(GA_PKG_DIR):
            if "__pycache__" in root or "node_modules" in root or "tests" in root:
                continue
            for file in files:
                if not file.endswith((".md", ".json", ".ts", ".py", ".sh")):
                    continue
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for token in forbidden:
                    self.assertNotIn(token, content, f"Forbidden reference '{token}' in {filepath}")


class TestValidateCommitExtension(unittest.TestCase):
    def test_extension_registers_native_guard(self):
        """extensions/validate-commit.ts intercepts bash tool calls natively."""
        ext_path = os.path.join(GA_PKG_DIR, "extensions", "validate-commit.ts")
        self.assertTrue(os.path.exists(ext_path))
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('pi.on("tool_call"', content)
        self.assertIn('isToolCallEventType("bash", event)', content)
        # Denies raw git commit and bare git add
        self.assertIn("git\\\\s+commit", content)
        self.assertIn("git\\\\s+add", content)
        self.assertIn("block: true", content)


class TestSessionContextExtension(unittest.TestCase):
    def test_extension_exists_and_registers_tool(self):
        """extensions/session-context.ts registers a session_context tool that reads session entries."""
        ext_path = os.path.join(GA_PKG_DIR, "extensions", "session-context.ts")
        self.assertTrue(os.path.exists(ext_path), "extensions/session-context.ts is missing")
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("session_context", content)
        self.assertIn("registerTool", content)
        self.assertIn("getEntries", content)
        self.assertIn('"message"', content)

    def test_commit_skill_prioritizes_session_context(self):
        """commit skill must instruct building the intent from session context, not a one-liner."""
        skill = os.path.join(GA_PKG_DIR, "skills", "commit", "SKILL.md")
        with open(skill, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("session_context", content)
        self.assertIn("intent", content)
        self.assertIn("session", content)

    def test_commit_and_push_skill_prioritizes_session_context(self):
        """commit-and-push skill must also build the intent from session context."""
        skill = os.path.join(GA_PKG_DIR, "skills", "commit-and-push", "SKILL.md")
        with open(skill, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("session_context", content)
        self.assertIn("intent", content)

    def test_commit_skill_no_longer_asks_for_one_sentence(self):
        """The one-sentence-intent instruction must be gone in favor of session-driven context."""
        skill = os.path.join(GA_PKG_DIR, "skills", "commit", "SKILL.md")
        with open(skill, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("one-sentence", content)
        self.assertNotIn("concise one-sentence", content)


if __name__ == "__main__":
    unittest.main()
