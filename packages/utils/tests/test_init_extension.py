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

    def built_prompt(self, *args: str) -> str:
        """The prompt /init actually sends, built by the extension itself."""
        script = f'''
import {{ buildInitPrompt }} from {json.dumps(INIT_EXTENSION.as_uri())};
console.log(JSON.stringify(buildInitPrompt("/tmp/example-repo"{", " + ", ".join(json.dumps(a) for a in args)})));
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
        return json.loads(result.stdout)

    def test_extension_file_exists_and_registers_command(self) -> None:
        self.assertTrue(INIT_EXTENSION.exists())

    def test_command_sends_the_prompt_immediately_when_idle(self) -> None:
        script = f'''
import ext from {json.dumps(INIT_EXTENSION.as_uri())};
const commands = {{}};
const sent = [];
const notifications = [];
ext({{
  registerCommand: (name, spec) => commands[name] = spec,
  sendUserMessage: (content, options) => sent.push({{ content, options }}),
}});
const base = {{
  cwd: "/tmp/example-repo",
  model: {{ provider: "test", id: "test-model" }},
  modelRegistry: {{ hasConfiguredAuth: () => true }},
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
}};
await commands["init"].handler("release commands", {{ ...base, isIdle: () => true }});
await commands["init"].handler("", {{ ...base, isIdle: () => false }});
console.log(JSON.stringify({{ sent, notifications }}));
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
        report = json.loads(result.stdout)
        idle, busy = report["sent"]
        # An idle session runs the task now; a busy one queues it and says so.
        # An omitted delivery option is dropped by JSON serialization.
        self.assertNotIn("options", idle)
        self.assertEqual(busy["options"], {"deliverAs": "followUp"})
        self.assertIn("/tmp/example-repo", idle["content"])
        self.assertIn("release commands", idle["content"])
        self.assertNotIn("release commands", busy["content"])
        self.assertEqual(len(report["notifications"]), 1)
        self.assertEqual(report["notifications"][0]["type"], "info")

    def test_rejected_delivery_is_reported_instead_of_lost(self) -> None:
        script = f'''
import ext from {json.dumps(INIT_EXTENSION.as_uri())};
const commands = {{}};
const notifications = [];
ext({{
  registerCommand: (name, spec) => commands[name] = spec,
  sendUserMessage: () => {{ throw new Error("Agent is already processing. Specify streamingBehavior."); }},
}});
const ctx = {{
  cwd: "/tmp/example-repo",
  model: {{ provider: "test", id: "test-model" }},
  modelRegistry: {{ hasConfiguredAuth: () => true }},
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
  isIdle: () => true,
}};
await commands["init"].handler("", ctx);
console.log(JSON.stringify({{ notifications }}));
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
        notifications = json.loads(result.stdout)["notifications"]
        # A lost guide task must not read as queued work.
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["type"], "error")
        self.assertIn("was not sent", notifications[0]["message"])
        self.assertIn("already processing", notifications[0]["message"])

    def test_follow_up_notice_does_not_claim_delivery(self) -> None:
        # pi.sendUserMessage returns void and the host reports a rejection on its
        # own channel, so the notice may state the request but never a delivery.
        script = f'''
import ext from {json.dumps(INIT_EXTENSION.as_uri())};
const commands = {{}};
const notifications = [];
const sent = [];
ext({{
  registerCommand: (name, spec) => commands[name] = spec,
  sendUserMessage: (content, options) => sent.push({{ content, options }}),
}});
const ctx = {{
  cwd: "/tmp/example-repo",
  model: {{ provider: "test", id: "test-model" }},
  modelRegistry: {{ hasConfiguredAuth: () => true }},
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
  isIdle: () => false,
}};
await commands["init"].handler("", ctx);
console.log(JSON.stringify({{ sent, notifications }}));
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
        report = json.loads(result.stdout)
        self.assertEqual(report["sent"][0]["options"], {"deliverAs": "followUp"})
        self.assertEqual(len(report["notifications"]), 1)
        self.assertEqual(report["notifications"][0]["type"], "info")
        message = report["notifications"][0]["message"]
        self.assertIn("requested as a follow-up", message)
        self.assertIn("reports any delivery failure", message)
        self.assertNotIn("queued", message)

    def test_no_model_is_reported_instead_of_sending_the_task(self) -> None:
        # The host rejects a delivery with no model on its own error channel, which
        # an extension cannot observe, so the precondition is reported here.
        script = f'''
import ext from {json.dumps(INIT_EXTENSION.as_uri())};
const commands = {{}};
const notifications = [];
const sent = [];
ext({{
  registerCommand: (name, spec) => commands[name] = spec,
  sendUserMessage: (content, options) => sent.push({{ content, options }}),
}});
const ctx = {{
  cwd: "/tmp/example-repo",
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
  isIdle: () => true,
}};
await commands["init"].handler("", ctx);
console.log(JSON.stringify({{ sent, notifications }}));
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
        report = json.loads(result.stdout)
        self.assertEqual(report["sent"], [])
        self.assertEqual(len(report["notifications"]), 1)
        self.assertEqual(report["notifications"][0]["type"], "error")
        self.assertIn("No model is selected", report["notifications"][0]["message"])

    def test_missing_credentials_are_reported_instead_of_a_silent_rejection(self) -> None:
        # The host reports a rejected delivery on its own error channel, so the
        # credential precondition is checked and reported here.
        script = f'''
import ext from {json.dumps(INIT_EXTENSION.as_uri())};
const commands = {{}};
const notifications = [];
const sent = [];
ext({{
  registerCommand: (name, spec) => commands[name] = spec,
  sendUserMessage: (content, options) => sent.push({{ content, options }}),
}});
const ctx = {{
  cwd: "/tmp/example-repo",
  model: {{ provider: "test", id: "test-model" }},
  modelRegistry: {{ hasConfiguredAuth: () => false }},
  ui: {{ notify: (message, type) => notifications.push({{ message, type }}) }},
  isIdle: () => true,
}};
await commands["init"].handler("", ctx);
console.log(JSON.stringify({{ sent, notifications }}));
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
        report = json.loads(result.stdout)
        self.assertEqual(report["sent"], [])
        self.assertEqual(len(report["notifications"]), 1)
        self.assertEqual(report["notifications"][0]["type"], "error")
        self.assertIn("no configured credentials", report["notifications"][0]["message"])
        self.assertIn("test/test-model", report["notifications"][0]["message"])

    def test_prompt_covers_repository_guides_and_nested_scopes(self) -> None:
        prompt = self.built_prompt()
        for phrase in (
            "Repository Guidelines",
            "find",
            "AGENTS.md",
            "current working directory",
            "nested",
            "independent scope",
            "do not overwrite",
            "No word quota",
            "git history",
        ):
            self.assertIn(phrase, prompt)

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

    def test_prompt_uses_repository_evidence_without_hardcoded_project_policies(self) -> None:
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
        for project_policy in (
            "@fradser/",
            "pi-kit",
            "pi-packages",
            "Pi-package",
            "workspace:*",
            "peerDependencies",
            "Pi automatically",
            "pnpm",
            "pytest",
            ".changeset",
        ):
            with self.subTest(project_policy=project_policy):
                self.assertNotIn(project_policy, prompt)
        self.assertIn("existing shared modules", prompt)
        self.assertIn("target repository's files and documentation", prompt)
        self.assertIn("Omit unsupported conventions", prompt)

    def test_prompt_handles_projects_without_git_metadata(self) -> None:
        prompt = self.built_prompt()
        self.assertIn("Outside a Git checkout", prompt)
        self.assertIn("starting directory as the project root", prompt)
        self.assertIn("git history only when available", prompt)

    def test_prompt_preserves_authored_paragraphs_and_bullets_without_manual_width_wraps(self) -> None:
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
        self.assertNotIn("\n\n\n", prompt)
        self.assertNotIn("\r", prompt)
        self.assertIn(
            "Treat the current working directory as the active scope for ./AGENTS.md.",
            prompt,
        )

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

    def test_prompt_audits_instruction_cost_and_decision_boundaries(self) -> None:
        prompt = self.built_prompt()
        for phrase in (
            "Read repository evidence as needed",
            "stale, redundant, or overprescriptive",
            "task-specific documentation pointers",
            "No word quota or mandatory section checklist",
            "verified safe local workflows",
            "genuine safety and approval boundaries",
            "completion and stopping conditions",
            "needless test runs",
            "across models",
            "short, precise triggers",
            "Do not edit skill files unless explicitly requested",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)
        for obsolete in (
            "200-400 words",
            "inspect all existing instruction files across the repository before editing anything",
            "Determine the project structure, source and test locations",
        ):
            self.assertNotIn(obsolete, prompt)

    def test_package_manifest_loads_extensions_directory(self) -> None:
        manifest = json.loads((UTILS_PKG_DIR / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pi"]["extensions"], ["./index.ts"])
        self.assertTrue((UTILS_PKG_DIR / "index.ts").is_file())


if __name__ == "__main__":
    unittest.main()
