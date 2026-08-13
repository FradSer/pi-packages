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
        self.assertIn('display: false', content)

    def test_input_interception_registered(self) -> None:
        content = self.ext_source()
        self.assertIn('pi.on("input"', content)
        self.assertIn('"continue"', content)
        self.assertNotIn('"继续"', content)
        self.assertIn('action: "handled"', content)

    def test_continuation_prompt_logic(self) -> None:
        content = self.ext_source()
        self.assertIn("buildContinuationPrompt", content)
        self.assertIn("getLastUserPrompt", content)
        self.assertIn('stopReason === "aborted"', content)
        self.assertIn("toolResult", content)
        self.assertIn("isError", content)

    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("extensions", manifest["pi"])
        self.assertIn("./extensions", manifest["pi"]["extensions"])


if __name__ == "__main__":
    unittest.main()
