"""Tests for the @fradser/github pi package.

Covers the pi-native interaction extension (gh_ask_merge / gh_confirm) and
guards the regression that removed the Claude Code Stop-hook closeout
mechanism (hooks/closeout-stop.sh, arm-closeout.sh, clear-closeout.sh) in
favor of native ctx.ui dialogs.
"""
from __future__ import annotations

import glob
import json
import os
import unittest

import yaml

GH_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestGithubPackageManifest(unittest.TestCase):
    def test_package_json_validity(self):
        """package.json is a valid Pi package manifest with skills + extensions."""
        with open(os.path.join(GH_PKG_DIR, "package.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "@fradser/github")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertIn("pi", data)
        self.assertIn("skills", data["pi"])
        self.assertIn("extensions", data["pi"])
        self.assertIn("@earendil-works/pi-coding-agent", data.get("peerDependencies", {}))

    def test_skills_frontmatter_validity(self):
        """All SKILL.md frontmatters use only Pi fields."""
        skill_files = glob.glob(os.path.join(GH_PKG_DIR, "skills", "**", "SKILL.md"), recursive=True)
        self.assertGreater(len(skill_files), 0, "No skills found in github package")
        for skill_file in skill_files:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split("---", 2)
            self.assertGreaterEqual(len(parts), 3, f"Missing YAML frontmatter in {skill_file}")
            data = yaml.safe_load(parts[1])
            self.assertIn("name", data)
            self.assertIn("description", data)
            for key in ("allowed-tools", "user-invocable", "model", "argument-hint"):
                self.assertNotIn(key, data, f"Claude-only frontmatter key {key} in {skill_file}")


class TestInteractiveExtension(unittest.TestCase):
    def test_extension_registers_native_tools(self):
        """extensions/interactive.ts registers gh_ask_merge and gh_confirm."""
        with open(os.path.join(GH_PKG_DIR, "extensions", "interactive.ts"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('name: "gh_ask_merge"', content)
        self.assertIn('name: "gh_confirm"', content)
        # Both tools must block on native dialogs, not conversation text.
        self.assertIn("ctx.ui", content)
        self.assertIn('ctx.mode !== "tui"', content)  # non-TUI degradation path


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

    def test_skills_use_native_tools(self):
        """Merge/confirm decision points instruct the native tools."""
        review_pr = os.path.join(GH_PKG_DIR, "skills", "review-pr", "SKILL.md")
        with open(review_pr, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("gh_ask_merge", content)
        closeout = os.path.join(GH_PKG_DIR, "skills", "review-pr", "references", "closeout.md")
        with open(closeout, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("gh_ask_merge", content)
        self.assertIn("gh_confirm", content)


if __name__ == "__main__":
    unittest.main()
