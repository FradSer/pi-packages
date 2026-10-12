import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
WORKTREE_EXTENSION = UTILS_PKG_DIR / "extensions" / "worktree.ts"


def rewrite(command: str) -> str:
    script = f"""
import {{ rewriteWorktreeAddCommand }} from {json.dumps(WORKTREE_EXTENSION.as_uri())};
console.log(JSON.stringify(rewriteWorktreeAddCommand({json.dumps(command)})));
"""
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
    return json.loads(result.stdout)


def rewrite_in(command: str, cwd: str) -> str:
    script = f"""
import {{ rewriteWorktreeAddCommand }} from {json.dumps(WORKTREE_EXTENSION.as_uri())};
console.log(JSON.stringify(rewriteWorktreeAddCommand({json.dumps(command)}, {{ cwd: {json.dumps(cwd)} }})));
"""
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
    return json.loads(result.stdout)


def make_git_repo(path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True)

    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    (path / "README.md").write_text("main\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")


class TestWorktreeExtension(unittest.TestCase):
    def test_rewrites_plain_add_into_pi_worktrees(self) -> None:
        self.assertEqual(
            rewrite("git worktree add ../foo feature/foo"),
            "mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo",
        )

    def test_preserves_lock_reason_branch_and_commitish(self) -> None:
        command = 'git worktree add --lock --reason "active task" -b feature/foo ../foo HEAD~1'
        self.assertEqual(
            rewrite(command),
            'mkdir -p .pi/worktrees && git worktree add --lock --reason "active task" -b feature/foo .pi/worktrees/foo HEAD~1',
        )

    def test_preserves_orphan_as_a_valueless_flag(self) -> None:
        self.assertEqual(
            rewrite("git worktree add --orphan ../foo"),
            "mkdir -p .pi/worktrees && git worktree add --orphan .pi/worktrees/foo",
        )
        self.assertEqual(
            rewrite("git worktree add --orphan=topic ../foo"),
            "git worktree add --orphan=topic ../foo",
        )

    def test_preserves_every_documented_boolean_worktree_add_option(self) -> None:
        command = (
            "git worktree add --no-force --no-detach --no-checkout --no-lock "
            "--no-orphan --no-quiet --no-track --no-guess-remote "
            "--no-relative-paths -B topic ../foo HEAD"
        )
        self.assertEqual(
            rewrite(command),
            "mkdir -p .pi/worktrees && git worktree add --no-force --no-detach "
            "--no-checkout --no-lock --no-orphan --no-quiet --no-track "
            "--no-guess-remote --no-relative-paths -B topic .pi/worktrees/foo HEAD",
        )

    def test_handles_quoted_and_escaped_paths_without_splitting_them(self) -> None:
        self.assertEqual(
            rewrite('git worktree add "../feature branch" "feature/foo with space"'),
            "mkdir -p .pi/worktrees && git worktree add '.pi/worktrees/feature branch' \"feature/foo with space\"",
        )
        self.assertEqual(
            rewrite(r"git worktree add ../feature\ branch feature/foo"),
            "mkdir -p .pi/worktrees && git worktree add '.pi/worktrees/feature branch' feature/foo",
        )

    def test_preserves_double_dash_before_a_dash_prefixed_path(self) -> None:
        self.assertEqual(
            rewrite("git worktree add -- ../-worktree feature/foo"),
            "mkdir -p .pi/worktrees && git worktree add -- .pi/worktrees/-worktree feature/foo",
        )

    def test_already_redirected_and_unsafe_basename_paths_are_left_untouched(self) -> None:
        for command in (
            "git worktree add .pi/worktrees/foo feature/foo",
            "git worktree add ./.pi/worktrees/foo feature/foo",
            "git worktree add ../project/.pi/worktrees feature/foo",
            "git worktree add .pi/worktrees feature/foo",
            "git worktree add ../.. feature/foo",
        ):
            with self.subTest(command=command):
                self.assertEqual(rewrite(command), command)

    def test_unsupported_shell_syntax_and_unknown_options_are_left_untouched(self) -> None:
        commands = (
            "git worktree add ../foo feature/foo && git status",
            "git worktree add ../foo feature/foo; git status",
            "git worktree add ../foo feature/foo | tee output",
            "git worktree add ../foo feature/foo > output",
            "git worktree add ../foo $(git branch --show-current)",
            "git worktree add --unknown ../foo feature/foo",
            "git worktree add --reason= ../foo feature/foo",
            "git worktree add --reason --lock ../foo feature/foo",
            "git worktree add ../* feature/foo",
            "git -C repo worktree add ../foo feature/foo",
            "git worktree add '../unterminated feature/foo",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(rewrite(command), command)

    def test_non_worktree_commands_are_ignored(self) -> None:
        self.assertEqual(rewrite("git worktree list"), "git worktree list")

    def test_redirect_targets_the_repository_root_not_the_shell_cwd(self) -> None:
        # The bash tool runs in the session cwd, so a command issued from a
        # subdirectory must still land in the repository's own managed
        # directory — the same place /enter-worktree and the isolation filters
        # look.
        with tempfile.TemporaryDirectory() as base:
            root = Path(base) / "repo"
            nested = root / "packages" / "app"
            nested.mkdir(parents=True)
            make_git_repo(root)
            canonical_root = Path(os.path.realpath(root))
            managed = canonical_root / ".pi" / "worktrees"

            from_root = rewrite_in("git worktree add ../foo feature/foo", str(root))
            self.assertEqual(
                from_root,
                "mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo",
            )

            from_subdirectory = rewrite_in("git worktree add ../foo feature/foo", str(nested))
            self.assertEqual(
                from_subdirectory,
                f"mkdir -p {managed} && git worktree add {managed}/foo feature/foo",
            )
            # Neither spelling depends on where the shell happens to be.
            self.assertIn(str(managed), from_subdirectory)
            self.assertNotIn(str(nested / ".pi"), from_subdirectory)

    def test_outside_a_repository_the_relative_spelling_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(
                rewrite_in("git worktree add ../foo feature/foo", outside),
                "mkdir -p .pi/worktrees && git worktree add .pi/worktrees/foo feature/foo",
            )

    def test_notification_names_the_directory_the_worktree_lands_in(self) -> None:
        # From a subdirectory the redirect is absolute, so the report must not
        # repeat the relative spelling that the command did not use.
        with tempfile.TemporaryDirectory() as base:
            root = Path(base) / "repo"
            nested = root / "packages" / "app"
            nested.mkdir(parents=True)
            make_git_repo(root)
            managed = Path(os.path.realpath(root)) / ".pi" / "worktrees"
            script = f"""
import fs from "node:fs";
import register from {json.dumps(WORKTREE_EXTENSION.as_uri())};
const handlers = new Map();
const notifications = [];
register({{ on: (name, handler) => handlers.set(name, handler) }});
const event = {{ toolName: "bash", input: {{ command: "git worktree add ../feature feature" }} }};
const ctx = {{
  cwd: {json.dumps(str(nested))},
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
}};
const blocked = await handlers.get("tool_call")(event, ctx);
console.log(JSON.stringify({{
  command: event.input.command,
  blocked: blocked ?? null,
  notifications,
  managed: {json.dumps(str(managed))},
}}));
"""
            result = subprocess.run(
                ["bun", "run", "-"],
                cwd=REPO,
                input=script,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
            report = json.loads(result.stdout)
            self.assertIn(f"{report['managed']}/feature", report["command"])
            info = [entry for entry in report["notifications"] if entry["type"] == "info"]
            self.assertEqual(len(info), 1)
            self.assertIn(f"{report['managed']}/feature", info[0]["message"])
            self.assertNotIn("redirected to .pi/worktrees/", info[0]["message"])


if __name__ == "__main__":
    unittest.main()
