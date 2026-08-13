import json
import os
import unittest

GIT_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = "git" + "-agent"

class TestGitPackageDecoupling(unittest.TestCase):
    def test_zero_git_agent_references(self):
        """Ensure git package has zero occurrences of git-agent in code, docs, and procedures."""
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
        self.assertEqual(data["name"], "@fradser/git")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertIn("pi", data)
        self.assertNotIn("skills", data["pi"], "git uses the /git menu, not skills")
        self.assertIn("extensions", data["pi"])
        self.assertIn("procedures", data.get("files", []))

    def test_skills_directory_removed(self):
        """The skill surface is gone — workflows live in procedures/ behind the /git menu."""
        self.assertFalse(os.path.exists(os.path.join(GIT_PKG_DIR, "skills")), "skills/ must be removed")

    def test_menu_extension_registers_command(self):
        """extensions/menu.ts registers the /git command with a select menu."""
        ext_path = os.path.join(GIT_PKG_DIR, "extensions", "menu.ts")
        self.assertTrue(os.path.exists(ext_path))
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('registerCommand("git"', content)
        self.assertIn("ctx.ui.select", content)
        self.assertIn("sendUserMessage", content)
        self.assertIn("deliverAs", content)
        self.assertIn("{{PKG_DIR}}", content)
        self.assertIn("{{WORKFLOW_TYPE}}", content)

    def test_procedures_exist_for_every_menu_item(self):
        """Every menu item maps to a procedure file under procedures/."""
        proc_dir = os.path.join(GIT_PKG_DIR, "procedures")
        for name in ("start.md", "finish.md", "commit.md", "commit-and-push.md"):
            self.assertTrue(os.path.exists(os.path.join(proc_dir, name)), f"{name} missing")
        with open(os.path.join(proc_dir, "start.md"), "r", encoding="utf-8") as f:
            start = f.read()
        with open(os.path.join(proc_dir, "finish.md"), "r", encoding="utf-8") as f:
            finish = f.read()
        self.assertIn("{{WORKFLOW_TYPE}}", start)
        self.assertIn("{{WORKFLOW_TYPE}}", finish)
        self.assertIn("gitflow-start-pipeline.md", start)
        self.assertIn("gitflow-finish-pipeline.md", finish)
        for name in ("commit.md", "commit-and-push.md"):
            with open(os.path.join(proc_dir, name), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("/skill:", content, f"{name} must not reference /skill:")
            self.assertIn("git commit", content)

    def test_worktree_extension_exists(self):
        """Verify extensions/worktree.ts exists and exports default function."""
        ext_path = os.path.join(GIT_PKG_DIR, "extensions", "worktree.ts")
        self.assertTrue(os.path.exists(ext_path))
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("rewriteWorktreeAddCommand", content)
        self.assertIn(".pi/worktrees/", content)

    def test_worktree_extension_notifies_on_rewrite(self):
        """The worktree rewrite must surface a native notification to the user."""
        ext_path = os.path.join(GIT_PKG_DIR, "extensions", "worktree.ts")
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("ctx.ui.notify", content)

    def test_start_pipeline_asks_in_conversation(self):
        """The start pipeline must ask the user in the conversation on ambiguous derivation."""
        pipeline = os.path.join(GIT_PKG_DIR, "references", "gitflow-start-pipeline.md")
        with open(pipeline, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("ask the user in the conversation", content)
        self.assertEqual(content.count("ask the user in the conversation"), 3, "feature/hotfix/release each get an ask path")

class TestRiskyGate(unittest.TestCase):
    """extensions/risky-gate.ts forces pi's native confirm dialog on destructive git commands."""

    def setUp(self):
        with open(os.path.join(GIT_PKG_DIR, "extensions", "risky-gate.ts"), "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_gate_extension_exists(self):
        """risky-gate.ts ships and registers a tool_call hook, not a tool."""
        self.assertIn('pi.on("tool_call"', self.content)
        self.assertNotIn("registerTool", self.content, "the gate is a hook, not a model tool")

    def test_force_push_is_gated(self):
        """git push -f / --force / --force-with-lease must be gated."""
        self.assertIn(r"git\s+push", self.content)
        self.assertIn("--force", self.content)

    def test_force_branch_delete_is_gated(self):
        """git branch -D must be gated."""
        self.assertIn(r"branch\s+-D", self.content)

    def test_reset_and_clean_are_gated(self):
        """git reset --hard and git clean -f must be gated."""
        self.assertIn(r"reset\s+--hard", self.content)
        self.assertIn(r"clean\s+-f", self.content)

    def test_force_worktree_remove_is_gated(self):
        """git worktree remove --force must be gated."""
        self.assertIn(r"worktree\s+remove", self.content)
        self.assertIn("--force", self.content)

    def test_uses_native_select_dialog_and_headless_block(self):
        """The gate pops pi's option-select dialog, rewrites the command, and blocks headless runs."""
        self.assertIn("ctx.ui.select", self.content)
        self.assertIn("block: true", self.content)
        self.assertIn("event.input.command", self.content)
        self.assertIn("ctx.hasUI", self.content)
        self.assertIn("ask the user in the conversation", self.content)

    def test_options_generated_by_model(self):
        """The options (and each option's command) are generated by the active model."""
        self.assertIn("ctx.model", self.content)
        self.assertIn("modelRegistry.complete", self.content)
        self.assertIn("Propose the alternative actions", self.content)
        self.assertIn("|||", self.content)

    def test_gitflow_pipeline_no_skill_references(self):
        """References must not point at the removed /commit skill surface."""
        for name in ("gitflow-start-pipeline.md", "gitflow-finish-pipeline.md", "invariants.md", "coauthor-attribution.md"):
            with open(os.path.join(GIT_PKG_DIR, "references", name), "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("/skill:", content, f"{name} must not reference /skill:")
            self.assertNotIn("{{", content, f"{name} must not contain unsubstituted placeholders")

if __name__ == "__main__":
    unittest.main()
