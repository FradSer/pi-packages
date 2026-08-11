import glob
import json
import os
import subprocess
import unittest
import yaml

GIT_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = "git" + "-agent"

class TestGitPackageDecoupling(unittest.TestCase):
    def test_zero_git_agent_references(self):
        """Ensure git package has zero occurrences of git-agent in code, docs, and skills."""
        for root, _, files in os.walk(GIT_PKG_DIR):
            if "__pycache__" in root or "tests" in root:
                continue
            for file in files:
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    self.assertNotIn(
                        FORBIDDEN,
                        content,
                        f"Found forbidden reference in {filepath}"
                    )

    def test_package_json_validity(self):
        """Verify package.json exists and is a valid Pi package manifest."""
        manifest_path = os.path.join(GIT_PKG_DIR, "package.json")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "git")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertIn("pi", data)
        self.assertIn("skills", data["pi"])
        self.assertIn("extensions", data["pi"])

    def test_skills_frontmatter_validity(self):
        """Verify all SKILL.md frontmatters in git package parse cleanly."""
        skill_files = glob.glob(os.path.join(GIT_PKG_DIR, "skills", "**", "SKILL.md"), recursive=True)
        self.assertGreater(len(skill_files), 0, "No skills found in git package")
        for skill_file in skill_files:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split("---", 2)
            self.assertGreaterEqual(len(parts), 3, f"Missing YAML frontmatter in {skill_file}")
            data = yaml.safe_load(parts[1])
            self.assertIn("name", data)
            self.assertIn("description", data)
            # Pi skill frontmatter: name + description (+ optional disable-model-invocation).
            # Claude-only fields (allowed-tools, user-invocable, model) are not used.
            for key in ("allowed-tools", "user-invocable", "model", "argument-hint"):
                self.assertNotIn(key, data, f"Claude-only frontmatter key {key} in {skill_file}")
            self.assertNotIn(FORBIDDEN, parts[1])

    def test_worktree_extension_exists(self):
        """Verify extensions/worktree.ts exists and exports default function."""
        ext_path = os.path.join(GIT_PKG_DIR, "extensions", "worktree.ts")
        self.assertTrue(os.path.exists(ext_path))
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("rewriteWorktreeAddCommand", content)
        self.assertIn(".pi/worktrees/", content)

if __name__ == "__main__":
    unittest.main()
