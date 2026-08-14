import json
import subprocess
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

    def test_feature_describes_safe_parsing_contract(self) -> None:
        feature = (UTILS_PKG_DIR / "features" / "worktree.feature").read_text(encoding="utf-8")
        self.assertIn("--lock", feature)
        self.assertIn("--lock", feature)
        self.assertIn("Quoted and escaped paths", feature)
        self.assertIn("unsupported shell syntax", feature)


if __name__ == "__main__":
    unittest.main()
