import json
import subprocess
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
INIT_EXTENSION = UTILS_PKG_DIR / "extensions" / "init.ts"


class TestInitExtension(unittest.TestCase):
    def ext_source(self) -> str:
        return INIT_EXTENSION.read_text(encoding="utf-8")

    def test_extension_file_exists_and_registers_command(self) -> None:
        self.assertTrue(INIT_EXTENSION.exists())
        content = self.ext_source()
        self.assertIn('registerCommand("init"', content)
        self.assertIn("buildInitPrompt", content)
        self.assertIn("sendUserMessage", content)

    def test_prompt_covers_repository_guides_and_nested_scopes(self) -> None:
        content = self.ext_source()
        for phrase in (
            "Repository Guidelines",
            "find",
            "AGENTS.md",
            "current working directory",
            "nested",
            "independent scope",
            "do not overwrite",
            "200-400 words",
            "git history",
            "pi-kit",
        ):
            self.assertIn(phrase, content)

    def test_prompt_includes_cwd_and_optional_focus(self) -> None:
        script = f'''
import {{ buildInitPrompt }} from {json.dumps(INIT_EXTENSION.as_uri())};
console.log(JSON.stringify({{
  prompt: buildInitPrompt("/tmp/example-repo", "focus on release commands"),
}}));
'''
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        prompt = json.loads(result.stdout)["prompt"]
        self.assertIn("/tmp/example-repo", prompt)
        self.assertIn("focus on release commands", prompt)
        self.assertIn("all existing AGENTS.md", prompt)
        self.assertIn("do not add parent-file references", prompt)
        self.assertIn("@fradser/pi-kit", prompt)

    def test_prompt_preserves_paragraphs_and_bullets_without_source_noise(self) -> None:
        script = f'''
import {{ buildInitPrompt }} from {json.dumps(INIT_EXTENSION.as_uri())};
console.log(JSON.stringify(buildInitPrompt("/tmp/example-repo")));
'''
        result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
        prompt = json.loads(result.stdout)
        self.assertIn("\n\n", prompt)
        self.assertIn("- Find all existing AGENTS.md", prompt)
        self.assertNotIn("\n ", prompt)
        self.assertNotIn("\n\n\n", prompt)
        self.assertNotIn("\r", prompt)

        multiline_script = f'''
import {{ buildInitPrompt }} from {json.dumps(INIT_EXTENSION.as_uri())};
console.log(JSON.stringify(buildInitPrompt("/tmp/example-repo", "focus on\\nrelease commands")));
'''
        multiline_result = subprocess.run(
            ["bun", "run", "-"],
            cwd=REPO,
            input=multiline_script,
            capture_output=True,
            text=True,
            check=False,
        )
        if multiline_result.returncode != 0:
            raise AssertionError(f"TypeScript execution failed:\n{multiline_result.stderr}")
        multiline_prompt = json.loads(multiline_result.stdout)
        self.assertIn("focus on release commands", multiline_prompt)
        self.assertNotIn("\r", multiline_prompt)

    def test_package_manifest_loads_extensions_directory(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pi"]["extensions"], ["./index.ts"])
        self.assertTrue((UTILS_PKG_DIR / "index.ts").is_file())


if __name__ == "__main__":
    unittest.main()
