import json
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]


class TestContinueExtension(unittest.TestCase):
    def ext_source(self) -> str:
        return (UTILS_PKG_DIR / "extensions" / "continue.ts").read_text(encoding="utf-8")

    def test_extension_file_exists_and_registers_command(self) -> None:
        content = self.ext_source()
        self.assertIn('registerCommand("continue"', content)
        self.assertNotIn('registerCommand("继续"', content)
        self.assertIn('sendMessage', content)

    def test_strict_continue_input_interception(self) -> None:
        content = self.ext_source()
        self.assertIn('pi.on("input"', content)
        self.assertIn('isContinuationKeyword', content)
        self.assertIn('"continue"', content)
        self.assertIn('"继续"', content)
        self.assertIn('"繼續"', content)

    def test_standalone_keyword_matching_only(self) -> None:
        content = self.ext_source()
        # Assert exact Set matching logic is present and no wildcards/substring matches exist
        self.assertIn("CONTINUE_SET = new Set", content)
        self.assertIn("CONTINUE_SET.has(normalized)", content)
        self.assertNotIn("includes(", content)
        self.assertNotIn("startsWith(", content)

    def test_continuation_prompt_logic(self) -> None:
        content = self.ext_source()
        self.assertIn("resolveContinuation", content)
        self.assertIn("getLastUserPrompt", content)
        self.assertIn('stopReason === "aborted"', content)
        self.assertIn("isInterrupted", content)

    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("extensions", manifest["pi"])
        self.assertIn("./extensions", manifest["pi"]["extensions"])


if __name__ == "__main__":
    unittest.main()
