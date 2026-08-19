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
    assert "Scenario: Multi-turn side questions include conversation history in the prompt" in feature
    assert "Scenario: Multi-turn overlay maintains turns and aggregates token usage" in feature
    assert "overlay does not display a redundant header title for the initial question" in feature
    assert "each conversation turn displays its question with You and its answer with btw" in feature
    assert "follow-up composer uses two full-width horizontal separators instead of a boxed frame" in feature
    assert "follow-up composer keeps equal spacing on both sides of the input area" in feature
    assert "overlay does not report nonexistent hidden lines" in feature
    assert "conversation separators are longer than the content text and centered" in feature
    assert "Scenario: Side answers render Markdown formatting" in feature
    assert "block-level Markdown at the start of an answer is not joined to the btw label" in feature
    assert "Scenario: Side answers are constrained to concise responses" in feature
    assert "Scenario: Side context stays compact" in feature
    assert "Scenario: Excessive side output is capped before display" in feature



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
    assert manifest["pi"]["extensions"] == ["./index.ts"]


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
    assert (PACKAGE / "index.ts").is_file(), "Extension entry point index.ts is missing"
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


def test_prompt_constrains_side_answer_length_and_shape() -> None:
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "150 words or 600 characters" in spawner
    assert "at most five short bullet points" in spawner
    assert "Do not repeat the question" in spawner
    assert "write a report" in spawner


def test_context_defaults_are_compact() -> None:
    context = (SRC / "context.ts").read_text(encoding="utf-8")
    assert "DEFAULT_MAX_MESSAGES = 4" in context
    assert "DEFAULT_MAX_CHARS = 4_000" in context


def test_output_cap_is_suitable_for_a_short_side_answer() -> None:
    spawner = (SRC / "spawner.ts").read_text(encoding="utf-8")
    assert "OUTPUT_CAP = 6_000" in spawner


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


def test_overlay_is_full_width_and_covers_main_input() -> None:
    index = (SRC / "index.ts").read_text(encoding="utf-8")
    assert '"bottom-center"' in index
    assert '"100%"' in index
    assert "margin: { bottom: 0 }" in index
    assert "maxAnswerBody" in (SRC / "overlay.ts").read_text(encoding="utf-8")


def test_index_registers_btw_command_and_uses_overlay() -> None:
    index = (SRC / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("btw"' in index
    assert "ctx.ui.custom" in index
    assert "overlay: true" in index
    assert "runBtw" in index


def test_prompt_builds_multi_turn_history() -> None:
    result = run_typescript(
        f"""
        import {{ buildBtwPrompt }} from {json.dumps((SRC / "spawner.ts").as_uri())};

        const promptWithoutHistory = buildBtwPrompt("Where is auth?", "some session context");
        const promptWithHistory = buildBtwPrompt(
          "Does it support JWT?",
          "some session context",
          [
            {{ question: "Where is auth?", answer: "Auth is in src/auth.ts" }},
          ]
        );

        console.log(JSON.stringify({{
          promptWithoutHistory,
          promptWithHistory,
          hasHistorySection: promptWithHistory.includes("=== Side conversation history ==="),
          hasFirstQuestion: promptWithHistory.includes("[User]: Where is auth?"),
          hasFirstAnswer: promptWithHistory.includes("[Assistant]: Auth is in src/auth.ts"),
          hasNewQuestion: promptWithHistory.includes("=== Side question ===\\nDoes it support JWT?"),
        }}));
        """
    )
    assert result["hasHistorySection"] is True
    assert result["hasFirstQuestion"] is True
    assert result["hasFirstAnswer"] is True
    assert result["hasNewQuestion"] is True


def test_overlay_handles_multi_turn_flow() -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay }} from {json.dumps((SRC / "overlay.ts").as_uri())};

        const askedTurns = [];
        let cancelled = false;

        const fakeTui = {{
          terminal: {{ rows: 40, columns: 80 }},
          requestRender: () => {{}},
        }};

        const style = {{
          accent: (s) => `[acc]${{s}}[/acc]`,
          muted: (s) => `[mut]${{s}}[/mut]`,
          dim: (s) => `[dim]${{s}}[/dim]`,
          border: (s) => `[bor]${{s}}[/bor]`,
          success: (s) => `[suc]${{s}}[/suc]`,
          error: (s) => `[err]${{s}}[/err]`,
          fg: (_c, s) => s,
        }};

        let resolveFirstTurn;
        const firstTurnPromise = new Promise((resolve) => {{ resolveFirstTurn = resolve; }});

        let resolveSecondTurn;
        const secondTurnPromise = new Promise((resolve) => {{ resolveSecondTurn = resolve; }});

        const overlay = createBtwOverlay(fakeTui, style, {{
          question: "Where is auth?",
          onCancel: () => {{ cancelled = true; }},
          onAsk: async (question, history, _signal) => {{
            askedTurns.push({{ question, history: [...history] }});
            if (askedTurns.length === 1) {{
              return firstTurnPromise;
            }}
            return secondTurnPromise;
          }},
        }});

        const initialLines = overlay.render(80);

        // Complete first turn
        resolveFirstTurn({{
          text: "Auth is in src/auth.ts.",
          usage: {{ input: 100, output: 50, cacheRead: 0, cacheWrite: 0, totalTokens: 150, cost: 0.001 }},
          timedOut: false,
          exitCode: 0,
          stderr: "",
        }});

        await new Promise((r) => setTimeout(r, 10));
        const turn1Lines = overlay.render(80);

        // Ask follow-up turn by simulating user typing and hitting Enter
        for (const char of "Does it use JWT?\\r") {{
          overlay.handleInput(char);
        }}

        await new Promise((r) => setTimeout(r, 10));
        const turn2LoadingLines = overlay.render(80);

        // Complete second turn
        resolveSecondTurn({{
          text: "Yes, it uses jsonwebtoken.",
          usage: {{ input: 150, output: 60, cacheRead: 0, cacheWrite: 0, totalTokens: 210, cost: 0.0015 }},
          timedOut: false,
          exitCode: 0,
          stderr: "",
        }});

        await new Promise((r) => setTimeout(r, 10));
        const turn2AnsweredLines = overlay.render(80);

        overlay.dispose();

        console.log(JSON.stringify({{
          askedTurns,
          initialLinesCount: initialLines.length,
          initialRendered: initialLines.join("\\n"),
          turn1Rendered: turn1Lines.join("\\n"),
          turn2LoadingRendered: turn2LoadingLines.join("\\n"),
          turn2AnsweredRendered: turn2AnsweredLines.join("\\n"),
        }}));
        """
    )

    asked_turns = result["askedTurns"]
    assert len(asked_turns) == 2
    assert asked_turns[0]["question"] == "Where is auth?"
    assert asked_turns[0]["history"] == []
    assert asked_turns[1]["question"] == "Does it use JWT?"
    assert asked_turns[1]["history"] == [{"question": "Where is auth?", "answer": "Auth is in src/auth.ts."}]

    initial_rendered = result["initialRendered"]
    assert "btw  Where is auth?" not in initial_rendered

    turn1_rendered = result["turn1Rendered"]
    assert "btw  Where is auth?" not in turn1_rendered
    assert "Where is auth?" in turn1_rendered
    assert "Auth is in src/auth.ts." in turn1_rendered
    assert "[acc]You[/acc]" in turn1_rendered
    assert "[acc]btw[/acc]" in turn1_rendered
    assert turn1_rendered.count("Where is auth?") == 1

    turn2_rendered = result["turn2AnsweredRendered"]
    assert "btw  Where is auth?" not in turn2_rendered
    assert "Where is auth?" in turn2_rendered
    assert "Auth is in src/auth.ts." in turn2_rendered
    assert "Does it use JWT?" in turn2_rendered
    assert "Yes, it uses jsonwebtoken." in turn2_rendered
    assert turn2_rendered.count("Where is auth?") == 1
    assert turn2_rendered.count("Does it use JWT?") == 1
    assert "360 tokens" in turn2_rendered
    assert "2 turns" in turn2_rendered
    assert "Follow-up" not in turn2_rendered
    assert "Ask a follow-up" not in turn2_rendered
    assert "[acc]btw[/acc]" in turn2_rendered
    assert "[mut]›[/mut]" in turn2_rendered
    assert "more lines" not in turn2_rendered
    assert "__BTW_CONVERSATION_SEPARATOR__" not in turn2_rendered
    assert "[bor]─" in turn2_rendered
    assert "╭" not in turn2_rendered
    assert "╰" not in turn2_rendered

    separator = "[bor]" + "─" * 80 + "[/bor]"
    assert turn2_rendered.count(separator) == 4
    overlay_source = (SRC / "overlay.ts").read_text(encoding="utf-8")
    assert "const rightSpace = Math.max" in overlay_source
    assert "leftSpace = Math.floor" in overlay_source


def test_overlay_renders_markdown_answers_and_separates_block_content() -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay }} from {json.dumps((SRC / "overlay.ts").as_uri())};

        const fakeTui = {{
          terminal: {{ rows: 40, columns: 100 }},
          requestRender: () => {{}},
        }};
        const style = {{
          accent: (s) => `[acc]${{s}}[/acc]`,
          muted: (s) => `[mut]${{s}}[/mut]`,
          dim: (s) => `[dim]${{s}}[/dim]`,
          border: (s) => `[bor]${{s}}[/bor]`,
          success: (s) => `[suc]${{s}}[/suc]`,
          error: (s) => `[err]${{s}}[/err]`,
          fg: (_c, s) => s,
        }};

        const overlay = createBtwOverlay(fakeTui, style, {{
          question: "What is this?",
          onCancel: () => {{}},
          onAsk: async () => ({{
            text: "# Heading\\n\\n**bold** and *italic*\\n\\n- one\\n- two\\n\\n```ts\\nconst answer = true;\\n```",
            timedOut: false,
            exitCode: 0,
            stderr: "",
          }}),
        }});
        await new Promise((resolve) => setTimeout(resolve, 10));
        const rendered = overlay.render(100).join("\\n");
        overlay.dispose();
        console.log(JSON.stringify({{ rendered }}));
        """
    )

    rendered = result["rendered"]
    assert "[acc]Heading[/acc]" in rendered
    assert "[acc]bold[/acc]" in rendered
    assert "[mut]italic[/mut]" in rendered
    assert "[acc]- [/acc]one" in rendered
    assert "const answer = true;" in rendered
    assert "[bor]```ts[/bor]" in rendered
    assert "[acc]btw[/acc]  [acc]Heading" not in rendered


def test_overlay_cancelling_followup_turn_preserves_previous_turns() -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay }} from {json.dumps((SRC / "overlay.ts").as_uri())};

        let cancelled = false;
        let turn2Aborted = false;

        const fakeTui = {{
          terminal: {{ rows: 30, columns: 80 }},
          requestRender: () => {{}},
        }};

        const style = {{
          accent: (s) => `[acc]${{s}}[/acc]`,
          muted: (s) => `[mut]${{s}}[/mut]`,
          dim: (s) => `[dim]${{s}}[/dim]`,
          border: (s) => `[bor]${{s}}[/bor]`,
          success: (s) => `[suc]${{s}}[/suc]`,
          error: (s) => `[err]${{s}}[/err]`,
          fg: (_c, s) => s,
        }};

        let resolveFirstTurn;
        const firstTurnPromise = new Promise((resolve) => {{ resolveFirstTurn = resolve; }});

        const overlay = createBtwOverlay(fakeTui, style, {{
          question: "First question",
          onCancel: () => {{ cancelled = true; }},
          onAsk: async (question, _history, signal) => {{
            if (question === "First question") return firstTurnPromise;
            signal.addEventListener("abort", () => {{ turn2Aborted = true; }});
            return new Promise(() => {{}}); // never resolves
          }},
        }});

        resolveFirstTurn({{
          text: "First answer",
          timedOut: false,
          exitCode: 0,
          stderr: "",
        }});
        await new Promise((r) => setTimeout(r, 10));

        // Submit follow-up question
        for (const char of "Second question\\r") {{
          overlay.handleInput(char);
        }}
        await new Promise((r) => setTimeout(r, 10));

        // Press Escape to cancel follow-up turn
        overlay.handleInput("\\x1b");
        await new Promise((r) => setTimeout(r, 10));

        const restoredLines = overlay.render(80);

        console.log(JSON.stringify({{
          cancelled,
          turn2Aborted,
          restoredText: restoredLines.join("\\n"),
        }}));
        """
    )

    assert result["cancelled"] is False
    assert result["turn2Aborted"] is True
    assert "First answer" in result["restoredText"]
    assert "Second question" not in result["restoredText"]


def test_overlay_handles_followup_turn_error_gracefully() -> None:
    result = run_typescript(
        f"""
        import {{ createBtwOverlay }} from {json.dumps((SRC / "overlay.ts").as_uri())};

        const fakeTui = {{
          terminal: {{ rows: 30, columns: 80 }},
          requestRender: () => {{}},
        }};

        const style = {{
          accent: (s) => `[acc]${{s}}[/acc]`,
          muted: (s) => `[mut]${{s}}[/mut]`,
          dim: (s) => `[dim]${{s}}[/dim]`,
          border: (s) => `[bor]${{s}}[/bor]`,
          success: (s) => `[suc]${{s}}[/suc]`,
          error: (s) => `[err]${{s}}[/err]`,
          fg: (_c, s) => s,
        }};

        let resolveFirstTurn;
        const firstTurnPromise = new Promise((resolve) => {{ resolveFirstTurn = resolve; }});

        const overlay = createBtwOverlay(fakeTui, style, {{
          question: "Q1",
          onCancel: () => {{}},
          onAsk: async (question) => {{
            if (question === "Q1") return firstTurnPromise;
            return {{
              text: "",
              timedOut: true,
              exitCode: 1,
              stderr: "",
            }};
          }},
        }});

        resolveFirstTurn({{
          text: "Answer 1",
          timedOut: false,
          exitCode: 0,
          stderr: "",
        }});
        await new Promise((r) => setTimeout(r, 10));

        // Submit follow-up question
        for (const char of "Q2\\r") {{
          overlay.handleInput(char);
        }}
        await new Promise((r) => setTimeout(r, 10));

        const rendered = overlay.render(80).join("\\n");
        overlay.dispose();

        console.log(JSON.stringify({{
          rendered,
          hasAnswer1: rendered.includes("Answer 1"),
          hasTimeoutError: rendered.includes("timed out"),
        }}));
        """
    )

    assert result["hasAnswer1"] is True
    assert result["hasTimeoutError"] is True


def test_readme_documents_read_only_guarantee() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "read-only" in readme
    assert "--no-session" in readme
    assert "bash" in readme
