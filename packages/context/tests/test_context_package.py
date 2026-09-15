"""Contract tests for the single-tool @fradser/pi-context package."""
from __future__ import annotations

import json
import os
import subprocess
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(relative: str) -> str:
    with open(os.path.join(PACKAGE, relative), encoding="utf-8") as file:
        return file.read()


class TestContextPackage(unittest.TestCase):
    def test_empty_success_retries_exactly_once(self) -> None:
        result = subprocess.run(
            ["node", os.path.join(PACKAGE, "tests/context_retry_harness.mts")],
            cwd=os.path.dirname(os.path.dirname(PACKAGE)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_research_widget_shows_running_status(self) -> None:
        result = subprocess.run(
            ["node", os.path.join(PACKAGE, "tests/context_widget_harness.mts")],
            cwd=os.path.dirname(os.path.dirname(PACKAGE)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_research_registers_running_widget_above_editor(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertIn('setWidget("context-research"', source)
        self.assertIn("aboveEditor", source)
        self.assertIn("PI_SPINNER_FRAMES", source)
        self.assertIn("PI_SPINNER_INTERVAL_MS", source)
        self.assertIn("startResearchWidget", source)
        self.assertIn("updateResearchWidget", source)
        self.assertIn("clearResearchWidget", source)
        self.assertIn("renderPiWidgetRow", source)
        self.assertIn("current.agentName", source)

    def test_context_rows_fit_runtime_width(self) -> None:
        result = subprocess.run(
            ["node", os.path.join(PACKAGE, "tests/context_rendering_harness.mts")],
            cwd=os.path.dirname(os.path.dirname(PACKAGE)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_research_child_uses_prompt_constrained_tools_without_sandbox_limits(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertIn('RESEARCH_TOOLS = ["read", "bash"]', source)
        self.assertNotIn("EXCLUDED_TOOLS", source)
        self.assertIn("minimal: true", source)
        self.assertIn("runPiWorker", source)
        self.assertIn("createPackageAgentRun", source)
        self.assertNotIn("readFileSync", source)
        self.assertIn("child.cancelled", source)
        self.assertIn("child.exitCode !== 0", source)
        self.assertIn("FINAL_ANSWER_RETRY_INSTRUCTION", source)
        self.assertIn("finalAnswerRetry = false", source)
        self.assertIn("returned no answer after retry", source)
        self.assertNotIn("sandbox-exec", source)
        self.assertNotIn("sandboxProfile", source)
        self.assertNotIn("mkdtempSync", source)
        self.assertNotIn("researchDirectory", source)
        self.assertNotIn("CHILD_TIMEOUT_MS", source)
        self.assertNotIn("timedOut", source)
        self.assertNotIn("spawnPiChild", source)
        self.assertNotIn("terminateChildProcess", source)

    def test_research_child_delegates_to_shared_worker(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertIn("runPiWorker", source)
        self.assertNotIn("function parseChildOutput", source)
        self.assertNotIn("parsePiWorkerOutput", source)

    def test_research_child_runs_without_temp_directory_overrides(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertNotIn("TMPDIR", source)
        self.assertNotIn("process.env.TMPDIR =", source)

    def test_research_prompt_limits_temp_clone_to_tmp(self) -> None:
        agent = read("agents/context-researcher.md")
        source = read("extensions/context-tools.ts")
        self.assertIn("git clone --depth=1", agent)
        self.assertIn("/tmp", agent)
        self.assertIn("remove it before answering", agent)
        self.assertIn("Never modify the caller's working directory", agent)
        self.assertIn("createPackageAgentRun({", source)
        self.assertIn('packageRootUrl: new URL("../", import.meta.url).href', source)

    def test_result_is_empty_without_completion_event(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertNotIn("MAX_CHARS", source)
        self.assertNotIn("truncateHead", source)
        self.assertNotIn("createToolLifecycleResultRenderer", source)
        self.assertNotIn('eventToolLifecycle("context"', source)
        self.assertNotIn('label: "researched"', source)
        self.assertIn('renderShell: "self"', source)
        self.assertIn("renderCall(_args, theme, context)", source)
        self.assertIn("renderResult(result, _options, theme, context)", source)
        self.assertIn('theme.bold("[agent]")', source)
        self.assertEqual(source.count("renderContextCall(context.toolCallId, theme)"), 1)
        self.assertIn("return { render: () => [], invalidate: () => {} };", source)
        self.assertIn('CONTEXT_AGENT_PATH = "agents/context-researcher.md"', source)
        self.assertIn('CONTEXT_AGENT_NAME = "conext-research"', source)
        self.assertIn("return { ...run, name: CONTEXT_AGENT_NAME };", source)
        self.assertNotIn("elegantContextAgentName", source)

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
            "edit and write are unavailable because only read and bash are allowlisted",
            "extension, skill, prompt-template, context-file, and theme discovery are disabled",
            "context package's bundled agents/context-researcher.md",
            "user research question is appended to that bundled agent prompt",
            "git clone with depth 1 under /tmp",
            "remove its temporary clone after inspection",
            "no sandbox",
            "no result truncation",
            "status widget above the editor",
            "`[agent] @conext-research started · agents/context-researcher.md` shape",
            "every research invocation uses the fixed @conext-research identity",
            "retains no agent memory between invocations",
            "identifies the child agent with the same @conext-research name",
            "latest tool, thinking, or answer activity",
            "newer activity replaces older activity",
            "widget clears when research completes",
            "completed tool contributes no second agent-start row",
            "does not render a `[context] researched` lifecycle row",
            "complete answer remains model-facing without transcript details",
            "Pi cancellation terminates the child process",
            "cancellation error rather than a partial answer",
            "Empty successful research retries for a final answer",
            "retries the research once with a prompt requiring a self-contained final answer",
            "only an empty retry reports that research returned no answer",
            "A failed child process does not return an answer",
        ):
            self.assertIn(phrase, feature)


if __name__ == "__main__":
    unittest.main()
