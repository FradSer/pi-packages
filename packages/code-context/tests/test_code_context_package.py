"""Tests for the @fradser/code-context pi package.

Guards the conversion from MCP sidecar servers (.mcp.json — pi has no built-in
MCP support) to native pi extension tools that call the public REST APIs
directly.
"""
from __future__ import annotations

import json
import os
import re
import unittest

CC_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCodeContextManifest(unittest.TestCase):
    def test_package_json_validity(self):
        """package.json is a valid Pi package manifest with skills + extensions."""
        with open(os.path.join(CC_PKG_DIR, "package.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "@fradser/code-context")
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


if __name__ == "__main__":
    unittest.main()
