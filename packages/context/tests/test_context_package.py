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
        self.assertIn("createLiveActivityWidget", source)
        self.assertIn('key: "context-research"', source)
        self.assertIn('placement: "aboveEditor"', source)
        self.assertIn("startResearchWidget", source)
        self.assertIn("updateResearchWidget", source)
        self.assertIn("clearResearchWidget", source)
        self.assertIn('identity: "researcher"', source)
        self.assertNotIn("current.agentName", source)

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
        self.assertIn("prompts", manifest["files"])
        self.assertNotIn("agents", manifest["files"])

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
        self.assertIn("buildContextResearchPrompt", source)
        self.assertNotIn("createPackageAgentRun", source)
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
        prompt = read("prompts/context-research.md")
        source = read("extensions/context-tools.ts")
        self.assertIn("git clone --depth=1", prompt)
        self.assertIn("/tmp", prompt)
        self.assertIn("remove it before answering", prompt)
        self.assertIn("Never modify the caller's working directory", prompt)
        self.assertIn("buildContextResearchPrompt({", source)
        self.assertIn("validateContextPromptTemplate", read("extensions/context-prompt.ts"))

    def test_context_prompt_builder_is_typed_and_fails_closed(self) -> None:
        source = read("extensions/context-prompt.ts")
        self.assertIn("export interface ContextResearchPromptBindings", source)
        self.assertIn("USER_RESEARCH_REQUEST", source)
        self.assertIn("unknown placeholder", source)
        self.assertIn("missing placeholder", source)
        self.assertIn("unresolved placeholder", source)
        result = subprocess.run(
            ["node", "--import", "tsx", os.path.join(PACKAGE, "tests/context_prompt_harness.mts")],
            cwd=os.path.dirname(os.path.dirname(PACKAGE)),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_result_uses_lifecycle_renderer_without_truncation(self) -> None:
        source = read("extensions/context-tools.ts")
        self.assertNotIn("MAX_CHARS", source)
        self.assertNotIn("truncateHead", source)
        self.assertIn("createStaticToolLifecycleResultRenderer", source)
        self.assertIn('eventToolLifecycle("context"', source)
        self.assertIn('label: "researched"', source)
        self.assertNotIn('label: "researching"', source)
        self.assertIn("options.isPartial", source)
        self.assertIn("wrapTextWithAnsi", source)
        self.assertIn('keyHint("app.tools.expand"', source)
        self.assertIn('renderShell: "self"', source)
        self.assertIn("renderCall(args, theme, _context)", source)
        self.assertIn("renderResult(result, options, theme, context)", source)
        self.assertIn('theme.bold("[context]")', source)
        self.assertEqual(source.count("renderContextCall(args.query, theme)"), 1)
        self.assertNotIn("CONTEXT_PROMPT_PATH", source)
        self.assertIn("formatResearchSubject", source)
        self.assertNotIn("CONTEXT_AGENT_NAME", source)
        self.assertNotIn("agentName", source)
        self.assertNotIn("agentPath", source)

    def test_documentation_describes_only_the_single_tool(self) -> None:
        for relative in ("README.md", "references/workflow.md", "prompts/context-research.md"):
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
            "typed prompt builder reads its bundled Markdown as a reference protocol rather than using the file as the prompt",
            "current research request, caller working directory, reference protocol, and completion contract",
            "complete user research question remains model-facing without becoming a prompt resource identity",
            "git clone with depth 1 under /tmp",
            "remove its temporary clone after inspection",
            "no sandbox",
            "no result truncation",
            "live activity widget above the editor",
            "`[context] research started · <research query>` shape",
            "concrete query is normalized and width-bounded for display",
            "different query produces a different started row",
            "row does not expose a Markdown prompt resource path",
            "retains no memory between invocations",
            "identifies the worker as researcher",
            "exactly one blank line follows the started row",
            "latest tool, thinking, or answer activity",
            "newer activity replaces older activity",
            "widget clears when research completes",
            "completed tool contributes no second worker-start row",
            "running tool renders no duplicate progress row",
            "compact expandable `[context] researched` lifecycle row when finished",
            "expanding the researched row reveals the complete answer without line truncation",
            "partial progress renders no transcript row while running",
            "successful blocks use toolSuccessBg",
            "failed and cancelled blocks use toolErrorBg",
            "expand hint comes from the app.tools.expand keybinding",
            "Pi cancellation terminates the child process",
            "cancellation error rather than a partial answer",
            "Empty successful research retries for a final answer",
            "retries the research exactly once with a prompt requiring a self-contained final answer",
            "without relying on hidden reasoning or prior tool output",
            "only an empty retry reports that research returned no answer",
            "A failed child process does not return an answer",
        ):
            self.assertIn(phrase, feature)


if __name__ == "__main__":
    unittest.main()
