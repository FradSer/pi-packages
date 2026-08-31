"""Tests for the @fradser/pi-context pi package.

Guards the conversion from MCP sidecar servers (.mcp.json — pi has no built-in
MCP support) to native pi extension tools that call the public REST APIs
directly, and the prompt-injected /context command that replaced the skill.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import unittest

CC_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel: str) -> str:
    with open(os.path.join(CC_PKG_DIR, rel), "r", encoding="utf-8") as f:
        return f.read()


class TestContextManifest(unittest.TestCase):
    def test_package_json_validity(self):
        """package.json is a valid Pi package manifest with extensions and references."""
        data = json.loads(read("package.json"))
        self.assertEqual(data["name"], "@fradser/pi-context")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertNotIn("skills", data.get("pi", {}), "skills section must be removed")
        self.assertIn("extensions", data["pi"])
        self.assertIn("extensions", data.get("files", []))
        self.assertIn("references", data.get("files", []))
        self.assertIn("@earendil-works/pi-coding-agent", data.get("peerDependencies", {}))
        self.assertIn("@earendil-works/pi-ai", data.get("peerDependencies", {}))
        self.assertIn("@earendil-works/pi-tui", data.get("peerDependencies", {}))
        self.assertIn("typebox", data.get("peerDependencies", {}))
        self.assertEqual(data.get("dependencies", {}).get("@fradser/pi-kit"), "workspace:*")
        self.assertNotIn(".mcp.json", data.get("files", []))
        self.assertNotIn("skills", data.get("files", []))

    def test_no_skill_directory(self):
        """The package ships no skills/ directory — guidance is prompt-injected."""
        self.assertFalse(
            os.path.exists(os.path.join(CC_PKG_DIR, "skills")),
            "skills/ must be removed — use prompt injection + /context command",
        )

    def test_no_mcp_server_config(self):
        """The MCP sidecar config must be gone (pi has no built-in MCP)."""
        self.assertFalse(
            os.path.exists(os.path.join(CC_PKG_DIR, ".mcp.json")),
            ".mcp.json must be removed — pi has no built-in MCP support",
        )


class TestModificationResearchGuidance(unittest.TestCase):
    def test_agents_md_names_native_tools(self):
        """Package maintainer guidance names each native context tool."""
        content = read("AGENTS.md")
        self.assertIn("context_deepwiki", content)
        self.assertIn("context_context7", content)
        self.assertIn("context_exa", content)
        self.assertIn("Before editing", content)


class TestContextToolsExtension(unittest.TestCase):
    def test_extension_registers_native_tools(self):
        """extensions/context-tools.ts registers the three REST tools."""
        content = read(os.path.join("extensions", "context-tools.ts"))
        self.assertIn('name: "context_deepwiki"', content)
        self.assertIn('name: "context_context7"', content)
        self.assertIn('name: "context_exa"', content)
        self.assertIn("mcp.deepwiki.com", content)
        self.assertIn("context7.com", content)
        self.assertIn("api.exa.ai", content)
        self.assertIn("mcp.exa.ai", content, "keyless public Exa endpoint missing")
        self.assertIn("EXA_API_KEY", content)
        self.assertIn("StringEnum", content)
        self.assertNotIn("Type.Union", content)

    def test_native_tools_own_their_lifecycle_transcript_surfaces(self):
        """Every native retrieval tool suppresses Pi defaults and uses pi-kit's lifecycle row."""
        content = read(os.path.join("extensions", "context-tools.ts"))
        self.assertIn('renderShell: "self"', content)
        self.assertIn("renderCall: emptyToolCall", content)
        self.assertIn("renderResult(result, options, theme, context)", content)
        self.assertIn("createToolLifecycleResultRenderer", content)
        self.assertIn("eventToolLifecycle", content)
        self.assertIn('eventToolLifecycle("context", subject', content)
        self.assertIn("detailLimit: 50", content)

    def test_workflow_reference_has_no_mcp_references(self):
        """The workflow reference routes to the native tools, never MCP servers."""
        content = read(os.path.join("references", "workflow.md"))
        self.assertNotIn("MCP", content)
        self.assertNotIn("mcp", content)

    def test_workflow_reference_names_native_tools(self):
        for tool in ("context_deepwiki", "context_context7", "context_exa"):
            self.assertIn(tool, read(os.path.join("references", "workflow.md")))

    def test_no_stale_exa_key_requirement_anywhere(self):
        """Exa works keyless — no shipped doc may claim EXA_API_KEY is required."""
        for rel in (
            "README.md",
            "AGENTS.md",
            os.path.join("references", "workflow.md"),
            os.path.join("extensions", "context-tools.ts"),
            os.path.join("extensions", "context-command.ts"),
        ):
            content = read(rel)
            self.assertNotIn("requires `EXA_API_KEY`", content, rel)
            self.assertNotIn("requires EXA_API_KEY", content, rel)
            self.assertNotIn("Requires the EXA_API_KEY", content, rel)
            self.assertNotIn("when `EXA_API_KEY` is set, else", content, rel)
            self.assertNotIn("when `EXA_API_KEY` is available", content, rel)


class TestContextCommandExtension(unittest.TestCase):
    def test_registers_context_command(self):
        content = read(os.path.join("extensions", "context-command.ts"))
        self.assertIn('registerCommand("context"', content)
        self.assertIn("sendMessage", content)
        self.assertIn('CONTEXT_WORKFLOW_MESSAGE_TYPE = "context-workflow"', content)
        self.assertIn("references", content)
        self.assertIn("workflow.md", content)

    def test_injects_guidance_into_system_prompt(self):
        content = read(os.path.join("extensions", "context-command.ts"))
        self.assertIn('pi.on("before_agent_start"', content)
        self.assertIn("systemPrompt", content)
        self.assertIn("context_deepwiki", content)
        self.assertIn("context_context7", content)
        self.assertIn("context_exa", content)
        self.assertIn("/context", content)

    def test_guidance_is_proactive_with_triggers(self):
        """Guidance must state trigger conditions, not a passive capability list."""
        content = read(os.path.join("extensions", "context-command.ts"))
        self.assertIn("proactively", content)
        self.assertIn("search/", content, "web-search trigger missing")
        self.assertIn("library or framework API", content)
        self.assertIn("public GitHub repository", content)

    def test_guidance_states_keyless_exa(self):
        """Guidance must state Exa needs no key — an unevaluated conditional gets skipped."""
        content = read(os.path.join("extensions", "context-command.ts"))
        self.assertIn("works without an API key", content)
        self.assertIn("EXA_API_KEY upgrades", content)
        self.assertNotIn("is unavailable", content)

    def test_context_command_sends_one_collapsible_workflow_message(self):
        """The full workflow is model context but renders as one expandable lifecycle row."""
        workspace_dir = os.path.dirname(os.path.dirname(CC_PKG_DIR))
        candidates = glob.glob(
            os.path.join(
                workspace_dir,
                "node_modules",
                ".pnpm",
                "esbuild@*",
                "node_modules",
                "esbuild",
                "bin",
                "esbuild",
            )
        )
        self.assertTrue(candidates, "test requires the workspace esbuild binary")
        build_dir = os.path.join(CC_PKG_DIR, ".test-build")
        extension = os.path.join(build_dir, "context-command.mjs")
        script = f"""
import assert from "node:assert/strict";
import {{ registerContextCommand }} from {json.dumps("file://" + extension)};

const commands = new Map();
const renderers = new Map();
const messages = [];
const pi = {{
  on() {{}},
  registerCommand(name, command) {{ commands.set(name, command); }},
  registerMessageRenderer(name, renderer) {{ renderers.set(name, renderer); }},
  sendMessage(message, options) {{ messages.push({{ message, options }}); }},
}};
registerContextCommand(pi);

const command = commands.get("context");
let waited = false;
await command.handler("react --method=context7", {{ cwd: process.cwd(), waitForIdle: async () => {{ waited = true; }} }});
assert.equal(waited, true);
assert.equal(messages.length, 1);
const [sent] = messages;
assert.equal(sent.message.customType, "context-workflow");
assert.equal(sent.message.display, true);
assert.deepEqual(sent.message.details.targets, ["react"]);
assert.deepEqual(sent.message.details.methods, ["context7"]);
assert.deepEqual(sent.options, {{ deliverAs: "followUp", triggerTurn: true }});
assert.match(sent.message.content, /Run the \\/context workflow/);

const renderer = renderers.get("context-workflow");
assert.ok(renderer, "context workflow needs a custom message renderer");
const theme = {{
  fg: (_color, text) => text,
  bg: (_color, text) => text,
  bold: (text) => text,
}};
const collapsed = renderer(sent.message, {{ expanded: false }}, theme).render(120).join("\\n");
const expanded = renderer(sent.message, {{ expanded: true }}, theme).render(120).join("\\n");
assert.match(collapsed, /\\[context\\] workflow · react · context7/);
assert.doesNotMatch(collapsed, /Retrieve code context for any repo/);
assert.match(expanded, /Run the \\/context workflow/);
assert.match(expanded, /Retrieve code context for any repo/);
"""
        try:
            os.makedirs(build_dir, exist_ok=True)
            build = subprocess.run(
                [
                    candidates[0],
                    "packages/context/extensions/context-command.ts",
                    "--bundle",
                    "--platform=node",
                    "--format=esm",
                    "--external:@earendil-works/pi-coding-agent",
                    "--external:@earendil-works/pi-tui",
                    "--external:@fradser/pi-kit",
                    f"--outfile={extension}",
                ],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(build.returncode, 0, f"{build.stderr}\\n{build.stdout}")
            result = subprocess.run(
                ["node", "--input-type=module", "--eval", script],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{result.stderr}\\n{result.stdout}")
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)

    def test_context_command_completes_without_stale_extensions_in_print_mode(self):
        """The command keeps single-shot Pi alive until the workflow completes."""
        workspace_dir = os.path.dirname(os.path.dirname(CC_PKG_DIR))
        result = subprocess.run(
            [
                "pi",
                "--print",
                "--mode",
                "json",
                "--no-session",
                "--tools",
                "context_context7",
                "/context react --method=context7",
            ],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"name":"context_context7"', result.stdout)
        self.assertIn('"type":"agent_settled"', result.stdout)
        self.assertNotIn("Extension error", result.stderr)
        self.assertNotIn("stale after session replacement or reload", result.stderr)


class TestReadmeContract(unittest.TestCase):
    def test_readme_has_no_mcp_claims(self):
        content = read("README.md")
        self.assertNotIn(".mcp.json", content)
        self.assertNotIn("MCP Servers Required", content)
        self.assertNotIn("Claude Code CLI", content)
        for tool in (
            "read_wiki_structure",
            "read_wiki_contents",
            "resolve-library-id",
            "query-docs",
            "get_code_context_exa",
        ):
            self.assertNotIn(tool, content, f"stale MCP tool name {tool} in README")

    def test_readme_advertises_context_command_only(self):
        """README documents /context, not any skill path."""
        content = read("README.md")
        self.assertIn("/context", content)
        self.assertIn("one expandable `[context] workflow` message", content)
        self.assertNotIn("/skill:context", content)
        self.assertNotIn("/skill:get-context", content)
        self.assertNotIn("/skill:code-context", content)
        self.assertNotIn("skills/", content)
        self.assertIn("optional manual prompt brief", content)

    def test_readme_version_matches_manifest(self):
        readme = read("README.md")
        manifest = json.loads(read("package.json"))
        self.assertIn(f"**Version:** {manifest['version']}", readme)


class TestFeatureContract(unittest.TestCase):
    def test_feature_does_not_reference_skills(self):
        feature = read(os.path.join("features", "native-tool-runtime.feature"))
        self.assertNotIn("/skill:", feature)
        for phrase in (
            "/context",
            "optional manual prompt brief",
            "Pi aborts the tool execution signal",
            "fails so Pi records an error result",
            "EXA_API_KEY is not configured",
            "configured request timeout elapses",
            "proactive use of context_exa",
            "proactive use of context_context7",
            "proactive use of context_deepwiki",
            "public keyless Exa endpoint at mcp.exa.ai",
            "EXA_API_KEY is configured",
            "queries api.exa.ai with the key",
            "states context_exa works without an API key",
        ):
            self.assertIn(phrase, feature)


class TestHttpBehavior(unittest.TestCase):
    def test_http_tools_forward_pi_abort_signal_and_timeout(self):
        content = read(os.path.join("extensions", "context-tools.ts"))
        self.assertIn("function requestSignal(signal: AbortSignal | undefined)", content)
        self.assertIn("AbortSignal.any", content)
        self.assertIn("AbortSignal.timeout(TIMEOUT_MS)", content)
        self.assertRegex(content, r"httpJson\([\s\S]*signal: AbortSignal \| undefined")
        self.assertRegex(content, r"deepwikiCall\([\s\S]*signal: AbortSignal \| undefined")

    def test_operational_http_failures_are_thrown_and_exa_needs_no_key(self):
        content = read(os.path.join("extensions", "context-tools.ts"))
        self.assertIn("throw new Error(`Context7 search failed", content)
        self.assertIn("throw new Error(`Context7 docs failed", content)
        self.assertIn("throw new Error(`Exa search failed", content)
        self.assertNotIn("catch (err)", content)
        self.assertNotIn("EXA_API_KEY is not set", content)
        self.assertIn("web_search_exa", content)

    def test_native_tools_abort_and_signal_operational_failures_at_runtime(self):
        workspace_dir = os.path.dirname(os.path.dirname(CC_PKG_DIR))
        candidates = glob.glob(
            os.path.join(
                workspace_dir,
                "node_modules",
                ".pnpm",
                "esbuild@*",
                "node_modules",
                "esbuild",
                "bin",
                "esbuild",
            )
        )
        self.assertTrue(candidates, "test requires the workspace esbuild binary")
        esbuild = candidates[0]
        build_dir = os.path.join(CC_PKG_DIR, ".test-build")
        os.makedirs(build_dir, exist_ok=True)
        extension = os.path.join(build_dir, "context-tools.mjs")
        try:
            build = subprocess.run(
                [
                    esbuild,
                    "packages/context/extensions/context-tools.ts",
                    "--bundle",
                    "--platform=node",
                    "--format=esm",
                    "--external:@earendil-works/pi-coding-agent",
                    "--external:@earendil-works/pi-ai",
                    "--external:typebox",
                    f"--outfile={extension}",
                ],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(build.returncode, 0, f"{build.stderr}\n{build.stdout}")
            result = subprocess.run(
                [
                    "node",
                    "--import",
                    "tsx",
                    "packages/context/tests/context_tools_harness.mts",
                    f"file://{extension}",
                ],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        finally:
            shutil.rmtree(build_dir)
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.stdout}")


if __name__ == "__main__":
    unittest.main()
