from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"


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


def test_feature_covers_isolation_and_temp_prompt_lifecycle() -> None:
    feature = (PACKAGE / "features" / "btw.feature").read_text(encoding="utf-8")
    assert "Feature: Read-only side questions" in feature
    assert "Scenario: A child Pi run is configured read-only" in feature
    assert "Scenario: A long side prompt exists only for the child lifetime" in feature
    assert "Scenario: A long side prompt is cleaned up when the child cannot launch" in feature


def test_long_prompt_temp_file_is_available_to_read_only_child_then_removed() -> None:
    result = run_typescript(
        f"""
        import {{ existsSync, readFileSync }} from "node:fs";
        import {{ mkdtemp, mkdir, readdir, rm, writeFile }} from "node:fs/promises";
        import {{ tmpdir }} from "node:os";
        import {{ join }} from "node:path";
        import {{ runBtw }} from {json.dumps((SRC / "spawner.ts").as_uri())};

        const sandbox = await mkdtemp(join(tmpdir(), "btw-spawner-success-"));
        const fakePi = join(sandbox, "fake-pi");
        const recordFile = join(sandbox, "child-record.json");
        await mkdir(join(fakePi, "bin"), {{ recursive: true }});
        await writeFile(join(fakePi, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const childScript = join(fakePi, "bin", "cli.mjs");
        await writeFile(childScript, `
          import {{ existsSync, writeFileSync }} from "node:fs";
          const args = process.argv.slice(1);
          const promptArg = args.find((arg) => arg.startsWith("@/"));
          writeFileSync(process.env.BTW_TEST_RECORD_FILE, JSON.stringify({{
            args,
            promptArg,
            promptExists: Boolean(promptArg && existsSync(promptArg.slice(1))),
          }}));
          process.stdout.write(JSON.stringify({{
            type: "message_end",
            message: {{ role: "assistant", content: [{{ type: "text", text: "verified" }}] }},
          }}) + "\\\\n");
        `);

        const originalArgv1 = process.argv[1];
        const originalTmpdir = process.env.TMPDIR;
        process.argv[1] = childScript;
        process.env.TMPDIR = sandbox;
        process.env.BTW_TEST_RECORD_FILE = recordFile;
        try {{
          const sideRun = await runBtw({{
            question: "Where is the implementation?",
            context: "x".repeat(8_001),
            cwd: sandbox,
            timeoutMs: 5_000,
          }});
          const record = JSON.parse(readFileSync(recordFile, "utf8"));
          const promptFile = record.promptArg.slice(1);
          console.log(JSON.stringify({{
            sideRun,
            record,
            promptStillExists: existsSync(promptFile),
            leftoverPromptDirectories: (await readdir(sandbox)).filter((name) => name.startsWith("btw-")),
          }}));
        }} finally {{
          process.argv[1] = originalArgv1;
          if (originalTmpdir === undefined) delete process.env.TMPDIR;
          else process.env.TMPDIR = originalTmpdir;
          delete process.env.BTW_TEST_RECORD_FILE;
          await rm(sandbox, {{ recursive: true, force: true }});
        }}
        """
    )

    record = result["record"]
    assert result["sideRun"]["text"] == "verified"
    assert record["promptExists"] is True
    assert record["args"][1:9] == [
        "--print",
        "--mode",
        "json",
        "--no-session",
        "--tools",
        "read,grep,find,ls",
        "--exclude-tools",
        "bash,edit,write",
    ]
    assert result["promptStillExists"] is False
    assert result["leftoverPromptDirectories"] == []


def test_long_prompt_temp_file_is_removed_when_child_launch_errors() -> None:
    result = run_typescript(
        f"""
        import {{ mkdtemp, mkdir, readdir, rm, writeFile }} from "node:fs/promises";
        import {{ tmpdir }} from "node:os";
        import {{ join }} from "node:path";
        import {{ runBtw }} from {json.dumps((SRC / "spawner.ts").as_uri())};

        const sandbox = await mkdtemp(join(tmpdir(), "btw-spawner-error-"));
        const fakePi = join(sandbox, "fake-pi");
        await mkdir(join(fakePi, "bin"), {{ recursive: true }});
        await writeFile(join(fakePi, "package.json"), JSON.stringify({{ name: "@earendil-works/pi-coding-agent" }}));
        const childScript = join(fakePi, "bin", "cli.mjs");
        await writeFile(childScript, "");

        const originalArgv1 = process.argv[1];
        const originalExecPath = process.execPath;
        const originalTmpdir = process.env.TMPDIR;
        process.argv[1] = childScript;
        process.execPath = join(sandbox, "missing-node");
        process.env.TMPDIR = sandbox;
        try {{
          const sideRun = await runBtw({{
            question: "What failed?",
            context: "x".repeat(8_001),
            cwd: sandbox,
            timeoutMs: 5_000,
          }});
          console.log(JSON.stringify({{
            sideRun,
            leftoverPromptDirectories: (await readdir(sandbox)).filter((name) => name.startsWith("btw-")),
          }}));
        }} finally {{
          process.argv[1] = originalArgv1;
          process.execPath = originalExecPath;
          if (originalTmpdir === undefined) delete process.env.TMPDIR;
          else process.env.TMPDIR = originalTmpdir;
          await rm(sandbox, {{ recursive: true, force: true }});
        }}
        """
    )

    assert result["sideRun"]["exitCode"] != 0
    assert result["leftoverPromptDirectories"] == []


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
