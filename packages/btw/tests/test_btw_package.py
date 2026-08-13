from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./src/index.ts"]


def test_extension_declares_peer_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "peerDependencies" in manifest
    for pkg in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui"):
        assert pkg in manifest["peerDependencies"]
        assert manifest["peerDependencies"][pkg] == "*"


def test_published_files_cover_extension_and_readme() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    assert "src" in files
    assert "README.md" in files


def test_extension_entry_point_exists() -> None:
    assert (SRC / "index.ts").is_file(), "Extension entry point src/index.ts is missing"
    assert (SRC / "spawner.ts").is_file(), "Spawner module src/spawner.ts is missing"
    assert (SRC / "context.ts").is_file(), "Context module src/context.ts is missing"
    assert (SRC / "overlay.ts").is_file(), "Overlay module src/overlay.ts is missing"
    assert not (SRC / "widget.ts").exists(), "Widget display was replaced by the interactive overlay"


def test_spawner_enforces_read_only_tool_scope() -> None:
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    # Allowlist is exactly the read-only builtin tools
    assert 'READ_ONLY_TOOLS = ["read", "grep", "find", "ls"]' in spawner
    # Writable/executable tools are always excluded
    assert '"bash", "edit", "write"' in spawner
    # The allowlist and exclusions must actually reach the child CLI args
    assert '"--tools"' in spawner
    assert '"--exclude-tools"' in spawner
    # The child must never persist a session
    assert '"--no-session"' in spawner


def test_spawner_parses_jsonl_output() -> None:
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "parseBtwOutput" in spawner
    assert "message_end" in spawner
    assert "totalTokens" in spawner


def test_prompt_builds_read_only_instructions() -> None:
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "buildBtwPrompt" in spawner
    assert "read-only tools (read, grep, find, ls)" in spawner
    assert "must NOT modify, create, or delete" in spawner


def test_prompt_does_not_specify_reply_language() -> None:
    """The prompt must not dictate the reply language — the model decides on its own."""
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "Answer concisely and directly." in spawner
    assert "always in English" not in spawner
    assert "same language as the question" not in spawner
    assert "language" not in spawner


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
    for path in sorted(SRC.glob("*.ts")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "Non-English (CJK) text found in src:\n" + "\n".join(offenders)


def test_context_is_conversation_excerpt() -> None:
    context = (SRC / "context.ts").read_text(encoding="utf-8")
    assert "buildConversationContext" in context
    assert "getBranch" in context
    assert '"user"' in context and '"assistant"' in context


def test_overlay_is_interactive_and_never_writes_to_session() -> None:
    overlay = (SRC / "overlay.ts").read_text(encoding="utf-8")
    assert "createBtwOverlay" in overlay
    assert "CancellableLoader" in overlay
    assert "handleInput" in overlay  # interactive: escape closes, keys scroll
    assert "Key.escape" in overlay
    assert "Key.pageUp" in overlay and "Key.pageDown" in overlay
    # The overlay must not append to the session manager — it only renders
    assert "sessionManager" not in overlay
    assert "appendEntry" not in overlay


def test_overlay_is_full_width_adaptive_popup() -> None:
    index = (SRC / "index.ts").read_text(encoding="utf-8")
    assert '"bottom-center"' in index
    assert '"100%"' in index
    assert "maxAnswerBody" in (SRC / "overlay.ts").read_text(encoding="utf-8")


def test_index_registers_btw_command_and_uses_overlay() -> None:
    index = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("btw"' in index
    assert "ctx.ui.custom" in index
    assert "overlay: true" in index
    assert "runBtw" in index


def test_readme_documents_read_only_guarantee() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "read-only" in readme
    assert "--no-session" in readme
    assert "bash" in readme
