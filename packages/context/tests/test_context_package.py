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
        self.assertIn("typebox", data.get("peerDependencies", {}))
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
        self.assertIn("EXA_API_KEY", content)
        self.assertIn("StringEnum", content)
        self.assertNotIn("Type.Union", content)

    def test_workflow_reference_has_no_mcp_references(self):
        """The workflow reference routes to the native tools, never MCP servers."""
        content = read(os.path.join("references", "workflow.md"))
        self.assertNotIn("MCP", content)
        self.assertNotIn("mcp", content)

    def test_workflow_reference_names_native_tools(self):
        for tool in ("context_deepwiki", "context_context7", "context_exa"):
            self.assertIn(tool, read(os.path.join("references", "workflow.md")))


class TestContextCommandExtension(unittest.TestCase):
    def test_registers_context_command(self):
        content = read(os.path.join("extensions", "context-command.ts"))
        self.assertIn('registerCommand("context"', content)
        self.assertIn("sendUserMessage", content)
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

    def test_operational_http_failures_are_thrown_but_missing_key_is_informational(self):
        content = read(os.path.join("extensions", "context-tools.ts"))
        self.assertIn("throw new Error(`Context7 search failed", content)
        self.assertIn("throw new Error(`Context7 docs failed", content)
        self.assertIn("throw new Error(`Exa search failed", content)
        self.assertNotIn("catch (err)", content)
        self.assertIn("EXA_API_KEY is not set", content)

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
