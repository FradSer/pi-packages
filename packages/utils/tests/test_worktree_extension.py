import json
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]


class TestWorktreeExtension(unittest.TestCase):
    def ext_source(self) -> str:
        return (UTILS_PKG_DIR / "extensions" / "worktree.ts").read_text(encoding="utf-8")

    def test_extension_file_exists_and_hooks_tool_call(self) -> None:
        content = self.ext_source()
        self.assertIn('pi.on("tool_call"', content)
        self.assertIn('isToolCallEventType("bash", event)', content)
        self.assertIn("rewriteWorktreeAddCommand", content)
        self.assertIn(".pi/worktrees/", content)

    def test_rewrites_plain_add_into_pi_worktrees(self) -> None:
        content = self.ext_source()
        self.assertIn("mkdir -p .pi/worktrees && git worktree add", content)
        self.assertIn('const targetPath = `.pi/worktrees/${basename}`', content)

    def test_already_redirected_path_is_left_untouched(self) -> None:
        content = self.ext_source()
        self.assertIn('originalPath.startsWith(".pi/worktrees/")', content)
        self.assertIn('originalPath.includes("/.pi/worktrees/")', content)

    def test_flags_with_values_are_preserved(self) -> None:
        content = self.ext_source()
        for flag in ('"-b"', '"-B"', '"--reason"', '"--lock"'):
            self.assertIn(flag, content)

    def test_non_worktree_commands_are_ignored(self) -> None:
        content = self.ext_source()
        self.assertIn('cmd.includes("worktree")', content)
        self.assertIn('cmd.includes("add")', content)

    def test_user_is_notified_of_the_redirect(self) -> None:
        content = self.ext_source()
        self.assertIn(
            "worktree path redirected to .pi/worktrees/ — linked worktrees stay inside the repo",
            content,
        )

    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("./extensions", manifest["pi"]["extensions"])
        self.assertIn("@earendil-works/pi-coding-agent", manifest["peerDependencies"])


if __name__ == "__main__":
    unittest.main()
