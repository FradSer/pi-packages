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
        self.assertIn('stopReason === "error"', content)
        self.assertIn('stopReason === "length"', content)
        self.assertIn('stopReason === "deferred"', content)
        self.assertIn('stopReason === "pending"', content)
        self.assertIn('stopReason === "toolUse"', content)
        self.assertIn("tool results were completed", content)
        self.assertIn("malformed", content)
        self.assertIn("context overflow recovery failed", content)
        self.assertIn("provider authentication is unavailable", content)
        self.assertIn("hasConfiguredAuth", content)
        self.assertIn("provider quota or billing limit is exhausted", content)
        self.assertIn("provider safety or content policy", content)
        self.assertIn("TRANSIENT_PROVIDER_ERROR_PATTERN", content)
        self.assertIn("other side closed", content)
        self.assertIn("ECONNRESET", content)
        self.assertIn("not recognized as a transient provider failure", content)
        self.assertIn("errorMessage", content)
        self.assertIn("isDirectContinuation", content)
        self.assertIn("stripDirectContinuationMessages", content)
        self.assertIn('pi.on("context"', content)
        self.assertIn('CONTINUATION_MESSAGE_TYPE = "continue-extension"', content)
        self.assertNotIn('pi.sendMessage(\n          {\n            customType: "continue-extension"', content)

    def test_feature_file_covers_provider_failure_recovery(self) -> None:
        feature = (UTILS_PKG_DIR / "features" / "continue.feature").read_text(encoding="utf-8")
        self.assertIn('stopReason "error"', feature)
        self.assertIn("provider is overloaded or the network timed out", feature)
        self.assertIn('stopReason "length"', feature)
        self.assertIn("Context overflow recovery has already failed", feature)
        self.assertIn("Provider authentication is unavailable", feature)
        self.assertIn("Provider quota or billing is exhausted", feature)
        self.assertIn("safety policy", feature)
        self.assertIn('stopReason "toolUse"', feature)
        self.assertIn('stopReason "pending"', feature)
        self.assertIn("arguments were truncated", feature)
        self.assertIn("non-retryable malformed request", feature)
        self.assertIn("unclassified provider error", feature)
        self.assertIn('latest assistant message has stopReason "stop"', feature)
        self.assertIn("without a continuation user message", feature)
        self.assertIn("omitted before the provider request", feature)
        self.assertIn("included in the model context", feature)
        self.assertIn('stopReason "stop"', feature)

    def test_feature_file_is_mirrored_in_project_memory(self) -> None:
        memory = (UTILS_PKG_DIR.parent.parent / ".memory" / "project_continue_recovery.md").read_text(encoding="utf-8")
        self.assertIn('stopReason: "error"', memory)
        self.assertIn("packages/utils/extensions/continue.ts", memory)

    def test_package_json_registers_extensions(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("extensions", manifest["pi"])
        self.assertIn("./extensions", manifest["pi"]["extensions"])


if __name__ == "__main__":
    unittest.main()
