import json
import os
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]


class TestEffortExtension(unittest.TestCase):
    def ext_source(self) -> str:
        return (UTILS_PKG_DIR / "extensions" / "effort.ts").read_text(encoding="utf-8")

    def test_extension_file_exists_and_registers_command(self) -> None:
        content = self.ext_source()
        self.assertIn('registerCommand("effort"', content)
        self.assertIn("setThinkingLevel", content)
        self.assertIn("getThinkingLevel", content)

    def test_canonical_levels_and_aliases(self) -> None:
        content = self.ext_source()
        for level in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
            self.assertIn(level, content)
        for alias in ("min", "med", "xh", "none", '"0"'):
            self.assertIn(alias, content)

    def test_unknown_level_rejected_with_hint(self) -> None:
        content = self.ext_source()
        self.assertIn("Unknown thinking level", content)

    def test_model_capability_narrows_the_menu(self) -> None:
        content = self.ext_source()
        self.assertIn("reasoning", content)
        self.assertIn("thinkingLevelMap", content)
        self.assertIn('return ["off"]', content)

    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("extensions", manifest["pi"])
        self.assertIn("./extensions", manifest["pi"]["extensions"])
        self.assertIn("peerDependencies", manifest)
        self.assertIn("@earendil-works/pi-coding-agent", manifest["peerDependencies"])

    def test_no_claude_only_artifacts(self) -> None:
        self.assertFalse((UTILS_PKG_DIR / ".claude-plugin").exists())


if __name__ == "__main__":
    unittest.main()
