from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
EXTENSIONS = PACKAGE / "extensions"
RECAP_URI = (EXTENSIONS / "recap.ts").as_uri()


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_feature_covers_recap_scenarios() -> None:
    feature = (PACKAGE / "features" / "recap.feature").read_text(encoding="utf-8")
    assert "Feature: Session Recap" in feature
    assert "Scenario: Recap shows after a turn" in feature
    assert "Scenario: Toggle recap on/off" in feature
    assert "Scenario: Generate recap manually" in feature


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./extensions"]


def test_extension_declares_peer_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "peerDependencies" in manifest
    assert "@earendil-works/pi-coding-agent" in manifest["peerDependencies"]
    assert manifest["peerDependencies"]["@earendil-works/pi-coding-agent"] == "*"


def test_published_files_cover_extension_and_readme() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    assert "extensions" in files
    assert "features" in files
    assert "README.md" in files


def test_extension_entry_point_exists() -> None:
    assert (EXTENSIONS / "index.ts").is_file()


def test_extension_uses_above_editor_widget() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'setWidget("recap"' in extension
    assert '"aboveEditor"' in extension


def test_extension_registers_recap_command() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("recap"' in extension


def test_extension_listens_to_agent_settled() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'pi.on("agent_settled"' in extension
    assert 'pi.on("input"' in extension


def test_extension_uses_settings_file() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "recapEnabled" in extension
    assert "autoRecap" in extension
    assert "recapModel" in extension
    assert "settings.json" in extension


def test_extension_spawns_child_process_for_recap() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "generateRecap" in extension
    assert "buildRecapPrompt" in extension
    assert "parseRecapOutput" in extension
    # Child process must not use tools
    assert '"--no-tools"' in extension
    # Child process must not create a session
    assert '"--no-session"' in extension


def test_recap_prompt_is_concise() -> None:
    recap = (EXTENSIONS / "recap.ts").read_text(encoding="utf-8")
    assert "Maximum 80 characters" in recap
    assert "Output ONLY the recap text" in recap
    assert "present tense" in recap


def test_extension_extracts_last_exchange() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "getLastExchange" in extension
    assert "getBranch" in extension


def test_extension_handles_toggle_subcommands() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert '/recap on' in extension or '"on"' in extension
    assert '/recap off' in extension or '"off"' in extension
    assert '/recap auto' in extension or '"auto"' in extension
    assert '/recap now' in extension or '"now"' in extension


def test_readme_documents_commands_and_settings() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "/recap" in readme
    assert "recapEnabled" in readme
    assert "autoRecap" in readme
    assert "recapModel" in readme
    assert "aboveEditor" in readme or "setWidget" in readme


def test_all_prompt_and_ui_strings_are_english() -> None:
    """All prompts and UI strings in the package source must be English — no CJK."""
    cjk = [
        "\\u4e00-\\u9fff",  # CJK Unified Ideographs
        "\\u3000-\\u303f",  # CJK Symbols and Punctuation
        "\\uff00-\\uffef",  # Fullwidth forms
    ]
    import re

    pattern = re.compile("[" + "".join(cjk) + "]")
    offenders: list[str] = []
    for path in sorted(EXTENSIONS.glob("*.ts")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "Non-English (CJK) text found in extensions:\n" + "\n".join(offenders)


def test_extract_last_exchange_logic() -> None:
    """Test the getLastExchange function with mock session entries."""
    result = run_typescript(
        f"""
        import {{ getLastExchange, extractMessageText }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", id: "1", parentId: null, timestamp: "2024-01-01T00:00:00Z", message: {{ role: "user", content: "hello" }} }},
            {{ type: "message", id: "2", parentId: "1", timestamp: "2024-01-01T00:00:01Z", message: {{ role: "assistant", content: "hi there" }} }},
            {{ type: "message", id: "3", parentId: "2", timestamp: "2024-01-01T00:00:02Z", message: {{ role: "user", content: "fix the bug" }} }},
            {{ type: "message", id: "4", parentId: "3", timestamp: "2024-01-01T00:00:03Z", message: {{ role: "assistant", content: "I found the issue in the API client" }} }},
        ];

        const exchange = getLastExchange(entries);
        console.log(JSON.stringify(exchange));
        """
    )
    assert result["user"] == "fix the bug"
    assert result["assistant"] == "I found the issue in the API client"


def test_extract_last_exchange_without_assistant() -> None:
    """getLastExchange returns undefined when there's no assistant message."""
    result = run_typescript(
        f"""
        import {{ getLastExchange }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", id: "1", parentId: null, timestamp: "2024-01-01T00:00:00Z", message: {{ role: "user", content: "hello" }} }},
        ];

        const exchange = getLastExchange(entries);
        console.log(JSON.stringify({{ hasExchange: exchange !== undefined, exchange: exchange ?? null }}));
        """
    )
    assert result["hasExchange"] is False
    assert result["exchange"] is None


def test_extract_message_text_string() -> None:
    """extractMessageText handles plain string content."""
    result = run_typescript(
        f"""
        import {{ extractMessageText }} from "{RECAP_URI}";

        const text = extractMessageText({{
            type: "message", id: "1", parentId: null, timestamp: "",
            message: {{ role: "user", content: "hello world" }}
        }});
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"] == "hello world"


def test_extract_message_text_array() -> None:
    """extractMessageText handles array content with text parts."""
    result = run_typescript(
        f"""
        import {{ extractMessageText }} from "{RECAP_URI}";

        const text = extractMessageText({{
            type: "message", id: "1", parentId: null, timestamp: "",
            message: {{ role: "assistant", content: [{{ type: "text", text: "answer" }}] }}
        }});
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"] == "answer"


def test_build_recap_prompt_has_instructions() -> None:
    """buildRecapPrompt includes the rules and the exchange."""
    result = run_typescript(
        f"""
        import {{ buildRecapPrompt }} from "{RECAP_URI}";

        const prompt = buildRecapPrompt("fix the login bug", "I checked the auth middleware");
        console.log(JSON.stringify({{
            hasRules: prompt.includes("Maximum 80 characters"),
            hasUser: prompt.includes("fix the login bug"),
            hasAssistant: prompt.includes("I checked the auth middleware"),
            hasPresentTense: prompt.includes("present tense"),
        }}));
        """
    )
    assert result["hasRules"] is True
    assert result["hasUser"] is True
    assert result["hasAssistant"] is True
    assert result["hasPresentTense"] is True


def test_parse_recap_output_extracts_text() -> None:
    """parseRecapOutput extracts the last assistant text from JSONL."""
    result = run_typescript(
        f"""
        import {{ parseRecapOutput }} from "{RECAP_URI}";

        const stdout = [
            JSON.stringify({{ type: "message_end", message: {{ role: "assistant", content: [{{ type: "text", text: "Fixing the login redirect bug" }}] }} }}),
        ].join("\\\\n");

        const text = parseRecapOutput(stdout);
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"] == "Fixing the login redirect bug"


def test_parse_recap_output_ignores_non_text() -> None:
    """parseRecapOutput ignores tool_use blocks and returns only text."""
    result = run_typescript(
        f"""
        import {{ parseRecapOutput }} from "{RECAP_URI}";

        const stdout = [
            JSON.stringify({{ type: "message_end", message: {{ role: "assistant", content: [
                {{ type: "text", text: "Refactoring the API client" }},
                {{ type: "tool_use", name: "bash", input: {{ command: "test" }} }},
            ]}}}}),
        ].join("\\\\n");

        const text = parseRecapOutput(stdout);
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"] == "Refactoring the API client"


def test_parse_recap_output_empty_on_no_message_end() -> None:
    """parseRecapOutput returns empty string when there's no message_end event."""
    result = run_typescript(
        f"""
        import {{ parseRecapOutput }} from "{RECAP_URI}";

        const stdout = JSON.stringify({{ type: "tool_execution_start", toolName: "bash", args: {{ }} }});
        const text = parseRecapOutput(stdout);
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"] == ""