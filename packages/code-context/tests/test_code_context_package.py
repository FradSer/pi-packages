"""Tests for the @fradser/pi-context pi package.

Guards the conversion from MCP sidecar servers (.mcp.json — pi has no built-in
MCP support) to native pi extension tools that call the public REST APIs
directly.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

CC_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCodeContextManifest(unittest.TestCase):
    def test_package_json_validity(self):
        """package.json is a valid Pi package manifest with skills + extensions."""
        with open(os.path.join(CC_PKG_DIR, "package.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "@fradser/pi-context")
        self.assertIn("pi-package", data.get("keywords", []))
        self.assertIn("skills", data["pi"])
        self.assertIn("extensions", data["pi"])
        self.assertIn("@earendil-works/pi-coding-agent", data.get("peerDependencies", {}))
        self.assertIn("@earendil-works/pi-ai", data.get("peerDependencies", {}))
        self.assertIn("typebox", data.get("peerDependencies", {}))
        self.assertNotIn(".mcp.json", data.get("files", []))

    def test_no_mcp_server_config(self):
        """The MCP sidecar config must be gone (pi has no built-in MCP)."""
        self.assertFalse(
            os.path.exists(os.path.join(CC_PKG_DIR, ".mcp.json")),
            ".mcp.json must be removed — pi has no built-in MCP support",
        )


class TestModificationResearchGuidance(unittest.TestCase):
    def test_maintainer_guidance_requires_applicable_native_context_tools(self):
        """Package changes document when each native context tool must be used."""
        with open(os.path.join(CC_PKG_DIR, "AGENTS.md"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("context_deepwiki", content)
        self.assertIn("context_context7", content)
        self.assertIn("context_exa", content)
        self.assertIn("Before editing", content)
        self.assertIn("applicable", content)
        self.assertIn("Change type", content)
        self.assertIn("fallback", content)


class TestContextToolsExtension(unittest.TestCase):
    def test_extension_registers_native_tools(self):
        """extensions/context-tools.ts registers the three REST tools."""
        with open(os.path.join(CC_PKG_DIR, "extensions", "context-tools.ts"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('name: "context_deepwiki"', content)
        self.assertIn('name: "context_context7"', content)
        self.assertIn('name: "context_exa"', content)
        # Direct HTTP calls, not MCP client infra
        self.assertIn("mcp.deepwiki.com", content)
        self.assertIn("context7.com", content)
        self.assertIn("api.exa.ai", content)
        self.assertIn("EXA_API_KEY", content)
        # Google-compatible string enums only
        self.assertIn("StringEnum", content)
        self.assertNotIn("Type.Union", content)

    def test_no_mcp_references_in_skills(self):
        """Skills must route to the native tools, never MCP servers."""
        for root, _, files in os.walk(os.path.join(CC_PKG_DIR, "skills")):
            for file in files:
                if not file.endswith(".md"):
                    continue
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertNotIn("MCP", content, f"MCP reference remains in {filepath}")
                self.assertNotIn("mcp", content, f"mcp reference remains in {filepath}")

    def test_skills_route_to_native_tools(self):
        """Skills name the native tools for each method."""
        for root, _, files in os.walk(os.path.join(CC_PKG_DIR, "skills")):
            for file in files:
                if not file.endswith(".md"):
                    continue
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                for tool in ("context_deepwiki", "context_context7", "context_exa"):
                    self.assertIn(tool, content, f"{tool} not referenced in {filepath}")

    def test_readme_has_no_mcp_claims(self):
        """README must not claim MCP servers are required."""
        with open(os.path.join(CC_PKG_DIR, "README.md"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn(".mcp.json", content)
        self.assertNotIn("MCP Servers Required", content)
        self.assertNotIn("Claude Code CLI", content)
        # No leftover MCP tool names
        for tool in ("read_wiki_structure", "read_wiki_contents", "resolve-library-id", "query-docs", "get_code_context_exa"):
            self.assertNotIn(tool, content, f"stale MCP tool name {tool} in README")

    def test_readme_advertises_only_executable_pi_surfaces(self):
        """README documents the real skill command and manual brief accurately."""
        with open(os.path.join(CC_PKG_DIR, "README.md"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("/skill:get-context", content)
        self.assertIn("optional manual prompt brief", content)
        self.assertNotIn("/get-context", content)
        self.assertNotIn("@context-researcher", content)

    def test_readme_version_matches_manifest(self):
        """Published documentation identifies the package's manifest version."""
        with open(os.path.join(CC_PKG_DIR, "README.md"), "r", encoding="utf-8") as f:
            readme = f.read()
        with open(os.path.join(CC_PKG_DIR, "package.json"), "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertIn(f"**Version:** {manifest['version']}", readme)

    def test_feature_covers_native_surface_and_error_contract(self):
        """BDD captures the documented surface and HTTP cancellation/error contract."""
        with open(os.path.join(CC_PKG_DIR, "features", "native-tool-runtime.feature"), "r", encoding="utf-8") as f:
            feature = f.read()
        for phrase in (
            "/skill:get-context",
            "optional manual prompt brief",
            "does not advertise /get-context or @context-researcher invocation",
            "Pi aborts the tool execution signal",
            "fails so Pi records an error result",
            "EXA_API_KEY is not configured",
            "configured request timeout elapses",
        ):
            self.assertIn(phrase, feature)

    def test_http_tools_forward_pi_abort_signal_and_timeout(self):
        """Provider HTTP shares Pi cancellation and still applies a bounded timeout."""
        with open(os.path.join(CC_PKG_DIR, "extensions", "context-tools.ts"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("function requestSignal(signal: AbortSignal | undefined)", content)
        self.assertIn("AbortSignal.any", content)
        self.assertIn("AbortSignal.timeout(TIMEOUT_MS)", content)
        self.assertRegex(content, r"httpJson\([\s\S]*signal: AbortSignal \| undefined")
        self.assertRegex(content, r"deepwikiCall\([\s\S]*signal: AbortSignal \| undefined")

    def test_operational_http_failures_are_thrown_but_missing_key_is_informational(self):
        """Pi receives failed tools for transport/provider failures, not key setup guidance."""
        with open(os.path.join(CC_PKG_DIR, "extensions", "context-tools.ts"), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("throw new Error(`Context7 search failed", content)
        self.assertIn("throw new Error(`Context7 docs failed", content)
        self.assertIn("throw new Error(`Exa search failed", content)
        self.assertNotIn("catch (err)", content)
        self.assertIn("EXA_API_KEY is not set", content)

    def test_native_tools_abort_and_signal_operational_failures_at_runtime(self):
        """The registered tools preserve missing-key guidance but throw cancellations and failures."""
        workspace_dir = os.path.dirname(os.path.dirname(CC_PKG_DIR))
        candidates = glob.glob(
            os.path.join(workspace_dir, "node_modules", ".pnpm", "esbuild@*", "node_modules", "esbuild", "bin", "esbuild")
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
                    "packages/code-context/extensions/context-tools.ts",
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
                ["node", "--import", "tsx", "packages/code-context/tests/context_tools_harness.mts", f"file://{extension}"],
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
