"""Contract tests for the single-tool @fradser/pi-context package."""
from __future__ import annotations

import json
import os
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(relative: str) -> str:
    with open(os.path.join(PACKAGE, relative), encoding="utf-8") as file:
        return file.read()


class TestContextPackage(unittest.TestCase):
    def test_manifest_is_native_extension_package(self) -> None:
        manifest = json.loads(read("package.json"))
        self.assertEqual(manifest["name"], "@fradser/pi-context")
        self.assertEqual(manifest["pi"]["extensions"], ["./index.ts"])
        self.assertIn("extensions", manifest["files"])
        self.assertIn("references", manifest["files"])
        self.assertIn("@earendil-works/pi-coding-agent", manifest["peerDependencies"])
        self.assertEqual(manifest["dependencies"]["@fradser/pi-kit"], "workspace:*")

    def test_context_registers_exactly_one_tool(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertEqual(source.count("pi.registerTool({"), 1)
        self.assertIn('name: "context_get"', source)
        self.assertNotIn("context_deepwiki", source)
        self.assertNotIn("context_context7", source)
        self.assertNotIn("context_exa", source)

    def test_package_has_no_context_command(self) -> None:
        source = read("extensions/context-command.ts")
        self.assertNotIn("registerCommand", source)
        self.assertNotIn('"context"', source)

    def test_research_child_is_isolated_and_read_only(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertIn('READ_ONLY_TOOLS = ["read", "bash"]', source)
        self.assertIn('EXCLUDED_TOOLS = ["edit", "write"]', source)
        self.assertIn('"--print"', source)
        self.assertIn('"--mode"', source)
        self.assertIn('"json"', source)
        self.assertIn('"--no-session"', source)
        self.assertIn('"--tools"', source)
        self.assertIn('"--exclude-tools"', source)
        self.assertIn("spawnPiChild", source)
        self.assertIn("terminateChildProcess", source)
        self.assertIn("CHILD_TIMEOUT_MS = 180_000", source)
        self.assertIn('process.platform === "darwin"', source)
        self.assertIn('command = sandboxed ? "sandbox-exec"', source)
        self.assertIn("(deny default)", source)
        self.assertIn("(allow file-write* (subpath", source)
        self.assertIn('realpathSync(mkdtempSync(join(tmpdir(), "pi-context-")))', source)
        self.assertIn("rmSync(researchDirectory, { recursive: true, force: true })", source)
        self.assertIn("child.cancelled", source)
        self.assertIn("child.timedOut", source)
        self.assertIn("child.exitCode !== 0", source)

    def test_research_prompt_limits_temp_clone_to_tmp(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertIn("git clone --depth=1", source)
        self.assertIn("/tmp", source)
        self.assertIn("remove it before answering", source)
        self.assertIn("Never modify the caller's working directory", source)

    def test_result_is_bounded_and_uses_lifecycle_renderer(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertIn("MAX_CHARS = 60_000", source)
        self.assertIn("truncateHead", source)
        self.assertIn("createToolLifecycleResultRenderer", source)
        self.assertIn('eventToolLifecycle("context", subject', source)
        self.assertIn('label: "researched"', source)
        self.assertIn('renderShell: "self"', source)
        self.assertIn("renderCall: emptyToolCall", source)

    def test_documentation_describes_only_the_single_tool(self) -> None:
        for relative in ("README.md", "references/workflow.md", "agents/context-researcher.md"):
            content = read(relative)
            self.assertIn("context_get", content, relative)
            self.assertNotIn("context_deepwiki", content, relative)
            self.assertNotIn("context_context7", content, relative)
            self.assertNotIn("context_exa", content, relative)

    def test_readme_explains_natural_language_trigger(self) -> None:
        content = read("README.md")
        self.assertIn("natural language", content)
        self.assertIn("invokes `context_get` automatically", content)
        self.assertIn("do not need to type `context_get`", content)

    def test_feature_records_single_tool_contract(self) -> None:
        feature = read("features/native-tool-runtime.feature")
        for phrase in (
            "only the context_get tool",
            "does not register a /context command",
            "print JSON mode without a session",
            "available tools are limited to read and bash",
            "edit and write are excluded",
            "git clone with depth 1 under /tmp",
            "removes its temporary clone",
            "Pi cancellation terminates the child process",
            "cancellation error rather than a partial answer",
            "A failed child process does not return an answer",
        ):
            self.assertIn(phrase, feature)


if __name__ == "__main__":
    unittest.main()
