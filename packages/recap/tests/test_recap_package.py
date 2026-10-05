from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
EXTENSIONS = PACKAGE / "extensions"
RECAP_URI = (EXTENSIONS / "recap.ts").as_uri()
INDEX_URI = (EXTENSIONS / "index.ts").as_uri()
CONFIG_URI = (EXTENSIONS / "config.ts").as_uri()
PIKIT_URI = (REPO / "packages" / "kit" / "src" / "index.ts").as_uri()


# Every extension-init harness reads `recap.json`, so an unisolated suite depends
# on whatever the developer machine happens to persist (including tests that
# toggle a preference, which then rewrote it). `autoRecap` is deliberately left
# unset here: the suite exercises the shipped cost policy, and only the tests
# about that policy name the preference explicitly.
ISOLATED_AGENT_DIR = """
import * as __fs from "node:fs";
import * as __os from "node:os";
import * as __path from "node:path";
const __agentDir = __fs.mkdtempSync(__path.join(__os.tmpdir(), "recap-agent-"));
process.env.PI_CODING_AGENT_DIR = __agentDir;
__fs.writeFileSync(
  __path.join(__agentDir, "recap.json"),
  JSON.stringify({ enabled: true, language: "auto" }),
  "utf-8",
);
"""


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=ISOLATED_AGENT_DIR + textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_notifications_use_pi_kits_portable_helper() -> None:
    source = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "notifyPi" in source
    assert "ctx.ui.notify(" not in source


def test_extension_registers_no_recap_entry_renderer() -> None:
    source = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "registerEntryRenderer" not in source

    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;

        const renderers = new Map();
        const extension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;
        extension({{
          on() {{}},
          registerCommand() {{}},
          appendEntry() {{}},
          registerEntryRenderer(type, renderer) {{ renderers.set(type, renderer); }},
        }});
        console.log(JSON.stringify({{ registeredTypes: [...renderers.keys()] }}));
        """
    )
    assert result["registeredTypes"] == []


def test_directory_recap_sync_uses_shared_canonical_identity_helpers() -> None:
    source = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "getDirectorySessionKey" in source
    assert "isSameDirectory" in source
    assert "replace(/^[/\\\\]/" not in source


def test_extract_latest_saved_recap_logic() -> None:
    result = run_typescript(
        f"""
        import {{ extractLatestSavedRecap }} from "{RECAP_URI}";

        const entries1 = [
            {{ type: "message", message: {{ role: "user", content: "hello" }} }},
            {{ type: "custom", customType: "recap", data: {{ recap: "First recap" }} }},
            {{ type: "message", message: {{ role: "user", content: "next step" }} }},
            {{ type: "custom", customType: "recap", data: {{ recap: "Second recap: updated auth" }} }},
        ];

        const entries2 = [
            {{ type: "message", message: {{ role: "user", content: "hello" }} }},
            {{ type: "custom", customType: "recap", data: {{ text: "Recap stored via text field" }} }},
        ];

        const entries3 = [
            {{ type: "message", message: {{ role: "user", content: "hello" }} }},
            {{ type: "custom", customType: "other", data: {{ recap: "Not a recap entry" }} }},
        ];

        const r1 = extractLatestSavedRecap(entries1);
        const r2 = extractLatestSavedRecap(entries2);
        const r3 = extractLatestSavedRecap(entries3);

        console.log(JSON.stringify({{ r1, r2, r3: r3 ?? null }}));
        """
    )
    assert result["r1"] == "Second recap: updated auth"
    assert result["r2"] == "Recap stored via text field"
    assert result["r3"] is None


def test_extract_latest_saved_recap_edge_cases() -> None:
    result = run_typescript(
        f"""
        import {{ extractLatestSavedRecap }} from "{RECAP_URI}";

        const empty = extractLatestSavedRecap([]);
        const notArray = extractLatestSavedRecap(null);
        const blank = extractLatestSavedRecap([
          {{ type: "custom", customType: "recap", data: {{ recap: "   " }} }},
        ]);
        const wrongType = extractLatestSavedRecap([
          {{ type: "custom", customType: "recap", data: {{ recap: 12345 }} }},
        ]);
        const missingData = extractLatestSavedRecap([
          {{ type: "custom", customType: "recap" }},
        ]);

        console.log(JSON.stringify({{
          empty: empty ?? null,
          notArray: notArray ?? null,
          blank: blank ?? null,
          wrongType: wrongType ?? null,
          missingData: missingData ?? null,
        }}));
        """
    )
    assert result["empty"] is None
    assert result["notArray"] is None
    assert result["blank"] is None
    assert result["wrongType"] is None
    assert result["missingData"] is None


def test_first_prompt_starts_recap_before_agent_settled_and_refreshes_after_completion() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let completeCalls = 0;
        let promptTexts = [];
        let appendedEntries = [];
        let resolveInitial;
        const initialCompletion = new Promise((resolve) => {{ resolveInitial = resolve; }});
        let branch = [];
        const widgetCalls = [];
        const fakePi = {{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry(customType, data) {{ appendedEntries.push({{ customType, data }}); }},
        }};
        initExtension(fakePi);
        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => branch,
            getSessionFile: () => undefined,
          }},
          ui: {{
            setWidget: (name, factory, options) => {{ widgetCalls.push({{ name, factory, options }}); }},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async (_model, request) => {{
              completeCalls++;
              promptTexts.push(request.messages[0].content[0].text);
              if (completeCalls === 1) await initialCompletion;
              return {{ role: "assistant", content: [{{ type: "text", text: `Recapped feature X (${{completeCalls}})` }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        await registeredEvents["session_start"]({{}}, fakeCtx);
        registeredEvents["input"]({{ source: "interactive", text: "Implement feature X" }}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 25));
        const callsBeforeSettled = completeCalls;
        const pendingWidget = widgetCalls.find((call) => call.name === "recap-activity" && call.factory)?.factory(
          {{ requestRender: () => {{}} }},
          {{ fg: (_name, text) => text, bold: (text) => text }},
        );
        const progressLines = pendingWidget?.render(80) ?? [];
        branch = [
          {{ type: "message", message: {{ role: "user", content: "Implement feature X" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "I implemented feature X" }} }},
        ];
        const settled = registeredEvents["agent_settled"]({{}}, fakeCtx);
        const settlementCompleted = await Promise.race([
          settled.then(() => true),
          new Promise((resolve) => setTimeout(() => resolve(false), 25)),
        ]);
        const callsAfterSettled = completeCalls;
        resolveInitial();
        await settled;
        await new Promise((resolve) => setTimeout(resolve, 25));
        await new Promise((resolve) => setTimeout(resolve, 25));

        console.log(JSON.stringify({{
          callsBeforeSettled,
          callsAfterSettled,
          settlementCompleted,
          finalCallCount: completeCalls,
          finalPromptHasAssistantOutcome: promptTexts[1]?.includes("I implemented feature X") ?? false,
          finalRecapPersisted: appendedEntries.some((entry) => entry.data.recap === "Recapped feature X (2)"),
          showsProgress: progressLines.some((line) => line.includes("Recapping...")),
          progressActivitySuffix: progressLines.some((line) => line.includes("Working...")),
          progressLeadingSpaces: progressLines.find((line) => line.includes("Recapping..."))?.match(/^ */)?.[0].length ?? 0,
        }}));
        """
    )
    assert result["callsBeforeSettled"] == 1
    assert result["callsAfterSettled"] == 1
    assert result["settlementCompleted"] is True
    assert result["finalCallCount"] == 2
    assert result["finalPromptHasAssistantOutcome"] is True
    assert result["finalRecapPersisted"] is True
    assert result["showsProgress"] is True
    assert result["progressActivitySuffix"] is False
    assert result["progressLeadingSpaces"] == 1


def test_generation_marker_replaces_the_recap_line() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let resolveCompletion;
        const pendingCompletion = new Promise((resolve) => {{ resolveCompletion = resolve; }});
        const widgetCalls = [];
        let branch = [
          {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "bug fixed in auth.ts" }} }},
          {{ type: "custom", customType: "recap", data: {{ recap: "Persisted: Fixed auth bug" }} }},
        ];
        const fakePi = {{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry() {{}},
        }};
        initExtension(fakePi);
        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => branch,
            getSessionFile: () => undefined,
          }},
          ui: {{
            setWidget: (name, factory, options) => {{ widgetCalls.push({{ name, factory, options }}); }},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              await pendingCompletion;
              return {{ role: "assistant", content: [{{ type: "text", text: "Recapped auth fix" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        const recapLineMounted = () =>
          widgetCalls.filter((call) => call.name === "recap").at(-1)?.factory !== undefined;

        await registeredEvents["session_start"]({{}}, fakeCtx);
        const mountedBeforeGeneration = recapLineMounted();
        branch = [
          ...branch,
          {{ type: "message", message: {{ role: "user", content: "add tests" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "auth tests added" }} }},
        ];
        registeredEvents["input"]({{ source: "interactive", text: "add tests" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 25));
        const mountedDuringGeneration = recapLineMounted();
        const markerFactory = widgetCalls.filter((call) => call.name === "recap-activity").at(-1)?.factory;
        const markerLines = markerFactory
          ? markerFactory({{ requestRender: () => {{}} }}, {{ fg: (_name, text) => text, bold: (text) => text }}).render(80)
          : [];
        resolveCompletion();
        await new Promise((resolve) => setTimeout(resolve, 25));
        console.log(JSON.stringify({{
          mountedBeforeGeneration,
          mountedDuringGeneration,
          markerLines,
          mountedAfterGeneration: recapLineMounted(),
        }}));
        """
    )
    assert result["mountedBeforeGeneration"] is True
    assert result["mountedDuringGeneration"] is False
    assert len(result["markerLines"]) == 1
    assert "Recapping..." in result["markerLines"][0]
    assert "Working..." not in result["markerLines"][0]
    assert result["mountedAfterGeneration"] is True


def test_session_replacement_aborts_pending_first_prompt_recap() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let completeCalls = 0;
        let signalAborted = false;
        let replacementWidgetFactory;
        let branch = [];
        const fakePi = {{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry() {{}},
        }};
        initExtension(fakePi);
        const createContext = (currentBranch) => ({{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => currentBranch, getSessionFile: () => undefined }},
          ui: {{
            setWidget: (_name, factory) => {{
              if (currentBranch.length > 0) replacementWidgetFactory = factory;
            }},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async (_model, _request, options) => {{
              completeCalls++;
              options.signal.addEventListener("abort", () => {{ signalAborted = true; }}, {{ once: true }});
              await new Promise((resolve) => setTimeout(resolve, 100));
              return {{ role: "assistant", content: [{{ type: "text", text: "stale recap" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }});

        const firstCtx = createContext(branch);
        await registeredEvents["session_start"]({{}}, firstCtx);
        registeredEvents["input"]({{ source: "interactive", text: "First session prompt" }}, firstCtx);
        await new Promise((resolve) => setTimeout(resolve, 20));
        await registeredEvents["session_start"](
          {{}},
          createContext([
            {{ type: "custom", customType: "recap", data: {{ recap: "Replacement recap" }} }},
          ]),
        );
        await new Promise((resolve) => setTimeout(resolve, 120));
        const replacementWidget = replacementWidgetFactory
          ? replacementWidgetFactory(
              {{ requestRender: () => {{}} }},
              {{ fg: (_name, text) => text }},
            )
          : undefined;
        const replacementLines = replacementWidget?.render(80) ?? [];

        console.log(JSON.stringify({{
          completeCalls,
          signalAborted,
          replacementPreserved: replacementLines.some((line) => line.includes("Replacement recap")),
          staleResultDiscarded: !replacementLines.some((line) => line.includes("stale recap")),
        }}));
        """
    )
    assert result["completeCalls"] == 1
    assert result["signalAborted"] is True
    assert result["replacementPreserved"] is True
    assert result["staleResultDiscarded"] is True


def test_generate_recap_cancellation_covers_auth_and_late_provider_results() -> None:
    result = run_typescript(
        f"""
        import {{ generateRecap }} from "{RECAP_URI}";

        const model = {{ provider: "mock", id: "m1" }};
        const response = {{ role: "assistant", content: [{{ type: "text", text: "late recap" }}] }};

        const preController = new AbortController();
        preController.abort();
        let preAuthCalls = 0;
        let preCompleteCalls = 0;
        const preResult = await generateRecap(
          {{
            getApiKeyAndHeaders: async () => {{ preAuthCalls++; return {{ ok: true, apiKey: "k", headers: {{}} }}; }},
            complete: async () => {{ preCompleteCalls++; return response; }},
          }}, model, "user", "assistant", undefined, "auto", preController.signal,
        );

        const authController = new AbortController();
        let resolveAuth;
        const authPending = new Promise((resolve) => {{ resolveAuth = resolve; }});
        let authCompleteCalls = 0;
        const authRequest = generateRecap(
          {{
            getApiKeyAndHeaders: async () => authPending,
            complete: async () => {{ authCompleteCalls++; return response; }},
          }}, model, "user", "assistant", undefined, "auto", authController.signal,
        );
        authController.abort();
        resolveAuth({{ ok: true, apiKey: "k", headers: {{}} }});
        const authResult = await authRequest;

        const lateController = new AbortController();
        let resolveComplete;
        let completeStartedResolve;
        const completeStarted = new Promise((resolve) => {{ completeStartedResolve = resolve; }});
        const lateResponse = new Promise((resolve) => {{ resolveComplete = resolve; }});
        const lateRequest = generateRecap(
          {{
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{ completeStartedResolve(); return lateResponse; }},
          }}, model, "user", "assistant", undefined, "auto", lateController.signal,
        );
        await completeStarted;
        lateController.abort();
        resolveComplete(response);
        const lateResult = await lateRequest;

        console.log(JSON.stringify({{
          preResult,
          preAuthCalls,
          preCompleteCalls,
          authResult,
          authCompleteCalls,
          lateResult,
        }}));
        """
    )
    assert result == {
        "preResult": "",
        "preAuthCalls": 0,
        "preCompleteCalls": 0,
        "authResult": "",
        "authCompleteCalls": 0,
        "lateResult": "",
    }


def test_startup_does_not_regenerate_when_saved_recap_exists() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let completeCalls = 0;

        const fakePi = {{
          on(event, handler) {{
            registeredEvents[event] = handler;
          }},
          registerCommand() {{}},
          appendEntry() {{}},
        }};

        initExtension(fakePi);

        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
              {{ type: "custom", customType: "recap", data: {{ recap: "Persisted: Already fixed" }} }},
            ],
            getSessionFile: () => "/tmp/fake-cwd/session-1.jsonl",
          }},
          ui: {{
            setWidget: () => {{}},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: "Regenerated" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        registeredEvents["session_start"]({{}}, fakeCtx);

        // Wait a short tick
        await new Promise((r) => setTimeout(r, 50));

        console.log(JSON.stringify({{ completeCalls }}));
        """
    )
    assert result["completeCalls"] == 0


def test_startup_regenerates_when_no_saved_recap_exists() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let completeCalls = 0;

        const fakePi = {{
          on(event, handler) {{
            registeredEvents[event] = handler;
          }},
          registerCommand() {{}},
          appendEntry() {{}},
        }};

        initExtension(fakePi);

        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
            ],
            getSessionFile: () => "/tmp/fake-cwd/session-1.jsonl",
          }},
          ui: {{
            setWidget: () => {{}},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: "Generated on startup" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        registeredEvents["session_start"]({{}}, fakeCtx);

        // Wait a short tick
        await new Promise((r) => setTimeout(r, 50));

        console.log(JSON.stringify({{ completeCalls }}));
        """
    )
    assert result["completeCalls"] == 1


def test_generate_recap_now_refreshes_an_existing_recap() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let registeredCommand;
        let completeCalls = 0;
        const fakePi = {{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand(_name, command) {{ registeredCommand = command; }},
          appendEntry() {{}},
        }};

        initExtension(fakePi);
        const fakeCtx = {{
          mode: "tui",
          hasUI: true,
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
              {{ type: "custom", customType: "recap", data: {{ recap: "Existing recap" }} }},
            ],
            getSessionFile: () => "/tmp/fake-cwd/session-1.jsonl",
          }},
          ui: {{
            setWidget: () => {{}},
            notify: () => {{}},
            select: async () => "Generate recap now",
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: "Refreshed recap" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        await registeredEvents["session_start"]({{}}, fakeCtx);
        await registeredCommand.handler("", fakeCtx);

        console.log(JSON.stringify({{ completeCalls }}));
        """
    )
    assert result["completeCalls"] == 1


def test_headless_session_does_not_start_recap_generation() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let completeCalls = 0;
        const fakePi = {{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry() {{}},
        }};

        initExtension(fakePi);
        const fakeCtx = {{
          mode: "json",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
            ],
            getSessionFile: () => undefined,
          }},
          ui: {{ setWidget: () => {{}}, notify: () => {{}} }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{ completeCalls++; return {{ role: "assistant", content: [{{ type: "text", text: "unexpected" }}] }}; }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        await registeredEvents["session_start"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 50));
        console.log(JSON.stringify({{ completeCalls }}));
        """
    )
    assert result["completeCalls"] == 0


def test_recap_now_command_refreshes_an_existing_recap() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredCommand;
        let completeCalls = 0;
        const fakePi = {{
          on() {{}},
          registerCommand(_name, command) {{ registeredCommand = command; }},
          appendEntry() {{}},
        }};
        initExtension(fakePi);
        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
            ],
            getSessionFile: () => undefined,
          }},
          ui: {{ setWidget: () => {{}}, notify: () => {{}} }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: "Refreshed recap" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};
        await registeredCommand.handler("now", fakeCtx);
        console.log(JSON.stringify({{ completeCalls }}));
        """
    )
    assert result["completeCalls"] == 1


def test_headless_recap_command_does_not_generate() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;
        let registeredCommand;
        let completeCalls = 0;
        const fakePi = {{
          on() {{}},
          registerCommand(_name, command) {{ registeredCommand = command; }},
          appendEntry() {{}},
        }};
        initExtension(fakePi);
        const fakeCtx = {{
          mode: "json",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => [
            {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
          ]}},
          ui: {{ setWidget: () => {{}}, notify: () => {{}} }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{ completeCalls++; return {{ role: "assistant", content: [{{ type: "text", text: "unexpected" }}] }}; }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};
        await registeredCommand.handler("now", fakeCtx);
        console.log(JSON.stringify({{ completeCalls }}));
        """
    )
    assert result["completeCalls"] == 0


def test_background_recap_handles_stale_append_without_unhandled_rejection() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;
        let registeredEvents = {{}};
        let unhandled = 0;
        process.on("unhandledRejection", () => {{ unhandled++; }});
        const fakePi = {{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry() {{ throw new Error("This extension ctx is stale after session replacement or reload."); }},
        }};
        initExtension(fakePi);
        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => [
            {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "bug fixed" }} }},
          ]}},
          ui: {{ setWidget: () => {{}}, notify: () => {{}} }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => ({{ role: "assistant", content: [{{ type: "text", text: "updated recap" }}] }}),
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};
        registeredEvents["input"]({{ source: "interactive" }});
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 50));
        console.log(JSON.stringify({{ unhandled }}));
        """
    )
    assert result["unhandled"] == 0


def test_extension_appends_entry_when_recap_generated() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let appendedEntries = [];

        const fakePi = {{
          on(event, handler) {{
            registeredEvents[event] = handler;
          }},
          registerCommand() {{}},
          appendEntry(customType, data) {{
            appendedEntries.push({{ customType, data }});
          }},
        }};

        initExtension(fakePi);

        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "Implement feature X" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "I implemented feature X" }} }},
            ],
            getSessionFile: () => "/tmp/fake-cwd/session-1.jsonl",
          }},
          ui: {{
            setWidget: () => {{}},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => ({{ provider: "mock", id: "m1" }}),
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => ({{
              role: "assistant",
              content: [{{ type: "text", text: "Implemented feature X in module" }}],
            }}),
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        // Simulate interactive turn
        registeredEvents["input"]({{ source: "interactive" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);

        // Wait a small tick for async performRecap promise
        await new Promise((r) => setTimeout(r, 50));

        console.log(JSON.stringify({{
          appendedCount: appendedEntries.length,
          entry: appendedEntries[0] ?? null,
        }}));
        """
    )
    assert result["appendedCount"] == 1
    assert result["entry"]["customType"] == "recap"
    assert result["entry"]["data"]["recap"] == "Implemented feature X in module"


def test_extension_restores_recap_from_session_branch_on_startup() -> None:
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let appendedEntries = [];
        let setWidgetCall = null;

        const fakePi = {{
          on(event, handler) {{
            registeredEvents[event] = handler;
          }},
          registerCommand() {{}},
          appendEntry(customType, data) {{
            appendedEntries.push({{ customType, data }});
          }},
        }};

        initExtension(fakePi);

        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed in auth.ts" }} }},
              {{ type: "custom", customType: "recap", data: {{ recap: "Persisted: Fixed auth bug in auth.ts" }} }},
            ],
            getSessionFile: () => "/tmp/fake-cwd/session-1.jsonl",
          }},
          ui: {{
            setWidget: (name, factory) => {{
              setWidgetCall = {{ name, factory }};
            }},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => undefined,
            getApiKeyAndHeaders: async () => ({{ ok: false }}),
          }},
          model: {{ provider: "test", id: "test-model" }},
        }};

        const sessionStartHandler = registeredEvents["session_start"];
        sessionStartHandler({{}}, fakeCtx);

        const fakeTheme = {{
          fg: (_name, text) => text,
        }};

        const widgetFactory = setWidgetCall?.factory;
        const widget = widgetFactory ? widgetFactory({{ requestRender: () => {{}} }}, fakeTheme) : null;
        const lines = widget ? widget.render(80) : [];

        console.log(JSON.stringify({{
          widgetSet: setWidgetCall !== null,
          widgetName: setWidgetCall?.name,
          lines,
          recapLeadingSpaces: lines.find((line) => line.includes("✦ Recap:"))?.match(/^ */)?.[0].length ?? 0,
        }}));
        """
    )
    assert result["widgetSet"] is True
    assert result["widgetName"] == "recap"
    assert any("Persisted: Fixed auth bug in auth.ts" in line for line in result["lines"])
    assert result["recapLeadingSpaces"] == 1

    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert (PACKAGE / "index.ts").is_file()


def test_recap_widget_never_marks_unclipped_content_as_truncated() -> None:
    """pi-tui's Markdown pads every rendered line to the requested width.

    Keeping that padding makes the composed row wider than the terminal, so the
    row fitter clips the padding and appends its ellipsis even though no recap
    content was dropped: the user sees a stray "..." at the end of a complete
    recap, and a second one mid-line for wide-character text.
    """
    recap = (
        "分析 pi-subagents 源码并对比 agent-teams，方案已写入 "
        "docs/spec-agent-teams-three-package-split.md，拟拆为 sub agent（含记忆）、task、agent teams"
    )
    result = run_typescript(
        f"""
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        const recap = {json.dumps(recap)};
        const registeredEvents = {{}};
        let setWidgetCall = null;

        initExtension({{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry() {{}},
        }});

        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix it" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "fixed" }} }},
              {{ type: "custom", customType: "recap", data: {{ recap }} }},
            ],
            getSessionFile: () => "/tmp/fake-cwd/session-1.jsonl",
          }},
          ui: {{
            setWidget: (name, factory) => {{ setWidgetCall = {{ name, factory }}; }},
            notify: () => {{}},
          }},
          modelRegistry: {{
            find: () => undefined,
            getApiKeyAndHeaders: async () => ({{ ok: false }}),
          }},
          model: {{ provider: "test", id: "test-model" }},
        }};

        registeredEvents["session_start"]({{}}, fakeCtx);
        const fakeTheme = {{ fg: (_name, text) => text }};
        const widget = setWidgetCall.factory({{ requestRender: () => {{}} }}, fakeTheme);

        const widths = [56, 80, 120, 200];
        const renderings = widths.map((width) => {{
          const lines = widget.render(width);
          const first = lines[0].replace(/^ ✦ Recap: /, "");
          const rest = lines.slice(1).map((line) => line.replace(/^ {{10}}/, ""));
          return {{
            width,
            rowWidths: lines.map(visibleWidth),
            renderedContent: [first, ...rest].join("").replace(/ +/g, ""),
            containsMarker: lines.some((line) => line.includes("...")),
          }};
        }});

        console.log(JSON.stringify({{ renderings }}));
        """
    )
    expected = "".join(recap.split())
    for rendering in result["renderings"]:
        assert max(rendering["rowWidths"]) <= rendering["width"], rendering
        content = re.sub(r"\x1b\[[0-9;]*m", "", rendering["renderedContent"])
        assert content == expected, rendering
        assert rendering["containsMarker"] is False, rendering


def test_extension_declares_peer_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "peerDependencies" in manifest
    assert "@earendil-works/pi-coding-agent" in manifest["peerDependencies"]
    assert "@earendil-works/pi-tui" in manifest["peerDependencies"]


def test_published_files_cover_extension_and_readme() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    assert "extensions" in files
    assert "features" in files
    assert "README.md" in files


def test_extension_entry_point_exists() -> None:
    assert (EXTENSIONS / "index.ts").is_file()
    assert (EXTENSIONS / "config.ts").is_file()
    assert (EXTENSIONS / "recap.ts").is_file()


def test_extension_uses_above_editor_widget() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'setWidget("recap"' in extension
    assert '"aboveEditor"' in extension


def test_extension_registers_recap_command_with_menu() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'registerCommand("recap"' in extension
    assert "openRecapMenu" in extension
    assert "chooseRecapModel" in extension
    assert "enterRecapModel" in extension
    assert "chooseRecapLanguage" in extension
    assert "Recapping..." in extension
    assert 'from "@fradser/pi-kit"' in extension
    assert "createLiveActivityWidget" in extension
    assert 'key: "recap-activity"' in extension
    assert 'identity: "Recapping..."' in extension
    assert "generatingRecap" in extension
    assert "starts with one leading space like native working rows" in (PACKAGE / "features" / "recap.feature").read_text(encoding="utf-8")


def test_recap_menu_merges_model_override_and_never_repeats_the_recap() -> None:
    result = run_typescript(
        f"""
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";

        const agentDir = fs.mkdtempSync(path.join(os.tmpdir(), "recap-menu-"));
        process.env.PI_CODING_AGENT_DIR = agentDir;
        const configPath = path.join(agentDir, "recap.json");
        fs.writeFileSync(configPath, JSON.stringify({{ provider: "old", model: "old-model", enabled: true, autoRecap: true, language: "auto" }}), "utf-8");

        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        const commands = {{}};
        initExtension({{
          on() {{}},
          registerCommand(name, definition) {{ commands[name] = definition; }},
          appendEntry() {{}},
        }});

        const selectCalls = [];
        const notices = [];
        const models = [{{ provider: "newprov", id: "new-model", name: "New Model" }}];
        let pickerResult;
        const fakeCtx = {{
          hasUI: true,
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => [], getSessionFile: () => undefined }},
          scopedModels: [],
          modelRegistry: {{ getAll: () => models, getAvailable: () => models, find: () => undefined }},
          model: {{ provider: "session", id: "session-model" }},
          ui: {{
            select: async (title, options) => {{
              selectCalls.push({{ title, options }});
              return options.find((option) => option.startsWith("Select recap model"));
            }},
            custom: async () => pickerResult,
            setWidget: () => {{}},
            notify: (message, level) => notices.push({{ message, level }}),
          }},
        }};

        pickerResult = undefined;
        await commands["recap"].handler("", fakeCtx);
        const clearedConfig = JSON.parse(fs.readFileSync(configPath, "utf-8"));

        pickerResult = {{ provider: "newprov", model: "new-model" }};
        await commands["recap"].handler("", fakeCtx);
        const selectedConfig = JSON.parse(fs.readFileSync(configPath, "utf-8"));
        await commands["recap"].handler("", fakeCtx);
        const selectedTitle = selectCalls.at(-1).title;
        const selectedOptions = selectCalls.at(-1).options;
        fs.rmSync(agentDir, {{ recursive: true, force: true }});

        console.log(JSON.stringify({{
          firstTitle: selectCalls[0].title,
          firstOptions: selectCalls[0].options,
          clearedConfig,
          selectedConfig,
          selectedTitle,
          selectedOptions,
          notices,
        }}));
        """
    )

    assert "Current recap" not in result["firstTitle"]
    assert "Model: old/old-model" in result["firstTitle"]
    assert [
        option for option in result["firstOptions"] if "model" in option.lower()
    ] == ["Select recap model (current: old/old-model)", "Enter provider/model manually"]
    assert "provider" not in result["clearedConfig"]
    assert "model" not in result["clearedConfig"]
    assert result["selectedConfig"]["provider"] == "newprov"
    assert result["selectedConfig"]["model"] == "new-model"
    assert "Select recap model (current: newprov/new-model)" in result["selectedOptions"]
    assert "Model: newprov/new-model" in result["selectedTitle"]
    assert {
        "message": "Recap model reset to session default",
        "level": "info",
    } in result["notices"]


def test_extension_listens_to_agent_settled_and_session_start() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'pi.on("agent_settled"' in extension
    assert 'pi.on("session_start"' in extension
    assert 'pi.on("input"' in extension


def test_thinking_only_response_is_not_used_as_recap() -> None:
    result = run_typescript(
        f"""
        import {{ textFromResponse }} from "{RECAP_URI}";

        const text = textFromResponse({{
          role: "assistant",
          content: [{{ type: "thinking", thinking: "private reasoning" }}],
        }});
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"] == ""


def test_extension_uses_model_registry_in_process() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    recap = (EXTENSIONS / "recap.ts").read_text(encoding="utf-8")
    assert "generateRecap" in extension
    assert "ctx.modelRegistry" in extension
    assert "resolveRecapModel" in extension
    assert "registry.complete" in recap
    assert "maxTokens: 512" in recap
    assert "RECAP_TIMEOUT_MS" in recap
    assert "AbortController" in recap
    # Must NOT use child_process spawn
    assert "child_process" not in extension
    assert "spawn(" not in extension


def test_recap_prompt_is_informative_and_concise() -> None:
    recap = (EXTENSIONS / "recap.ts").read_text(encoding="utf-8")
    assert "informative session recap generator" in recap
    assert "single-line recap" in recap


def test_build_recap_prompt_with_and_without_previous_recap() -> None:
    result = run_typescript(
        f"""
        import {{ buildRecapPrompt }} from "{RECAP_URI}";

        const p1 = buildRecapPrompt("add tests for auth", "I created test_auth.ts", "Refactored auth middleware");
        const p2 = buildRecapPrompt("add tests for auth", "I created test_auth.ts");

        console.log(JSON.stringify({{
            hasPrevious: p1.includes("Refactored auth middleware") && p1.includes("=== Previous recap ==="),
            noPrevious: !p2.includes("=== Previous recap ==="),
        }}));
        """
    )
    assert result["hasPrevious"] is True
    assert result["noPrevious"] is True


def test_first_prompt_recap_prompt_distinguishes_planned_work_from_completed_work() -> None:
    result = run_typescript(
        f"""
        import {{ buildRecapPrompt }} from "{RECAP_URI}";

        const prompt = buildRecapPrompt(
          "参考 /Users/FradSer/Documents/Home Lab/esp32-keyboard，我希望在 firmware/linux/ 开发遥控器，先实践左右滑动联动 HDMI 屏幕翻页",
          "",
        );

        console.log(JSON.stringify({{
          identifiesStartingWork: prompt.includes("starting") || prompt.includes("planned"),
          forbidsUnsupportedClaims: prompt.includes("Do not claim") && prompt.includes("not evidenced"),
          distinguishesAccessFromConnection: prompt.includes("not evidence that a connection was made"),
          includesUserRequest: prompt.includes("firmware/linux/") && prompt.includes("HDMI"),
        }}));
        """
    )
    assert result["identifiesStartingWork"] is True
    assert result["forbidsUnsupportedClaims"] is True
    assert result["distinguishesAccessFromConnection"] is True
    assert result["includesUserRequest"] is True


def test_build_recap_prompt_language_rules() -> None:
    result = run_typescript(
        f"""
        import {{ buildRecapPrompt }} from "{RECAP_URI}";

        const pAuto = buildRecapPrompt("user", "assistant", undefined, "auto");
        const pZh = buildRecapPrompt("user", "assistant", undefined, "zh");
        const pEn = buildRecapPrompt("user", "assistant", undefined, "en");
        const pCustom = buildRecapPrompt("user", "assistant", undefined, "Japanese");

        console.log(JSON.stringify({{
            pAutoHasConvLang: pAuto.includes("same language as the conversation"),
            pZhHasChinese: pZh.includes("Always output in Chinese"),
            pEnHasEnglish: pEn.includes("Always output in English"),
            pCustomHasLang: pCustom.includes("Always output in Japanese"),
        }}));
        """
    )
    assert result["pAutoHasConvLang"] is True
    assert result["pZhHasChinese"] is True
    assert result["pEnHasEnglish"] is True
    assert result["pCustomHasLang"] is True


def test_clean_recap_text_removes_prefixes_and_quotes() -> None:
    result = run_typescript(
        f"""
        import {{ cleanRecapText }} from "{RECAP_URI}";

        const t1 = cleanRecapText('"※ Recap: Refactoring auth middleware."');
        const t2 = cleanRecapText('```\\nSummary: Fixing the redirect bug\\n```');
        const t3 = cleanRecapText('- Updating the test configuration.');
        const t4 = cleanRecapText('“修复登录重定向问题。”');

        console.log(JSON.stringify({{ t1, t2, t3, t4 }}));
        """
    )
    assert result["t1"] == "Refactoring auth middleware"
    assert result["t2"] == "Fixing the redirect bug"
    assert result["t3"] == "Updating the test configuration"
    assert result["t4"] == "修复登录重定向问题"


def test_generate_recap_allows_reasoning_models_enough_completion_tokens() -> None:
    recap = (EXTENSIONS / "recap.ts").read_text(encoding="utf-8")
    assert "maxTokens: 512" in recap


def test_manual_recap_distinguishes_missing_exchange_from_generation_failure() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "No complete user/assistant exchange is available to recap" in extension
    assert "Recap generation failed; check the configured model and authentication" in extension
    assert "No recent exchange to recap or generation failed" not in extension


def test_generate_recap_retries_empty_or_meaningless_output_once() -> None:
    result = run_typescript(
        f"""
        import {{ generateRecap }} from "{RECAP_URI}";

        const outputs = ["修正Adaptive", "修正 Adaptive 配置，避免窄屏布局错误切换"];
        let completeCalls = 0;
        const prompts = [];
        const recap = await generateRecap(
          {{
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async (_model, request) => {{
              prompts.push(request.messages[0].content[0].text);
              const text = outputs[completeCalls++] ?? "";
              return {{ role: "assistant", content: [{{ type: "text", text }}] }};
            }},
          }},
          {{ provider: "mock", id: "m1" }},
          "fix recap",
          "updated adaptive layout handling",
        );

        console.log(JSON.stringify({{
          recap,
          completeCalls,
          retryRequestsSpecificity: prompts[1]?.includes("Previous output was rejected") ?? false,
        }}));
        """
    )
    assert result["recap"] == "修正 Adaptive 配置，避免窄屏布局错误切换"
    assert result["completeCalls"] == 2
    assert result["retryRequestsSpecificity"] is True


def test_generate_recap_does_not_retry_provider_failure() -> None:
    result = run_typescript(
        f"""
        import {{ generateRecap }} from "{RECAP_URI}";

        let completeCalls = 0;
        const recap = await generateRecap(
          {{
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              throw new Error("rate limited");
            }},
          }},
          {{ provider: "mock", id: "m1" }},
          "fix recap",
          "updated adaptive layout handling",
        );

        console.log(JSON.stringify({{ recap, completeCalls }}));
        """
    )
    assert result == {"recap": "", "completeCalls": 1}


def test_generate_recap_returns_empty_after_two_uninformative_outputs() -> None:
    result = run_typescript(
        f"""
        import {{ generateRecap }} from "{RECAP_URI}";

        let completeCalls = 0;
        const recap = await generateRecap(
          {{
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: completeCalls === 1 ? "" : "Fix Adaptive" }}] }};
            }},
          }},
          {{ provider: "mock", id: "m1" }},
          "fix recap",
          "updated adaptive layout handling",
        );

        console.log(JSON.stringify({{ recap, completeCalls }}));
        """
    )
    assert result == {"recap": "", "completeCalls": 2}


def test_clean_recap_text_preserves_inline_code_backticks() -> None:
    result = run_typescript(
        f"""
        import {{ cleanRecapText }} from "{RECAP_URI}";

        const text = cleanRecapText('`list_directory_sessions` 渲染对齐 monitor event 风格，重启后测试通过，数据链路正常');
        console.log(JSON.stringify({{ text }}));
        """
    )
    assert result["text"].startswith("`list_directory_sessions`")
    assert result["text"].count("`") == 2


def test_clean_recap_text_caps_length() -> None:
    result = run_typescript(
        f"""
        import {{ cleanRecapText }} from "{RECAP_URI}";

        const longText = "A".repeat(300);
        const cleaned = cleanRecapText(longText);

        console.log(JSON.stringify({{ len: cleaned.length }}));
        """
    )
    assert result["len"] == 120


def test_extension_wraps_recap_text_responsively() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    # Recaps wrap through pi-tui's Markdown at the width left over by the row
    # prefix, and that component's own padding is dropped again so the com-
    # posed row is never clipped into a truncation marker.
    assert "const contentWidth = Math.max(15, width - prefixWidth - WIDGET_LEADING_SPACES);" in extension
    assert "recapMarkdown.render(contentWidth)" in extension
    assert "raw.trimEnd()" in extension


def test_recap_markdown_is_built_once_and_not_per_rendered_frame() -> None:
    """The recap widget re-renders on every terminal frame while the agent streams.

    Building the pi-kit theme style and a new Markdown component inside
    `render()` repeated that work per frame (packages/btw/src/overlay.ts and
    pi-kit's own live-activity row both cache the instance), so the instance is
    now cached and only the text is swapped when the recap changes.
    """
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "function renderRecapMarkdown(" in extension
    assert "recapMarkdown.setText(currentRecap);" in extension
    assert "recapMarkdown.invalidate();" in extension
    assert extension.count("new Markdown(") == 1
    assert (
        extension.index("function renderRecapMarkdown(")
        < extension.index("new Markdown(")
        < extension.index("function updateRecapWidget(")
    ), "the Markdown instance must be built by the cached renderer, not by render()"


def test_headless_sessions_skip_recap_widget_and_generation() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "if (ctx.mode !== \"tui\") return;" in extension
    assert 'if (ctx.mode === "tui" && config.enabled && !savedRecap)' in extension
    # Automatic recapping now answers to the cost policy rather than to a raw
    # config flag, but it is still gated behind the TUI mode and display.
    assert 'if (ctx.mode !== "tui" || !config.enabled || !autoRecapDecision(ctx).enabled) return;' in extension
    assert 'ctx.mode === "tui" && config.enabled &&' in extension


def test_widget_refresh_ignores_disposed_context() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "function updateRecapWidget(ctx: ExtensionContext): void" in extension
    assert "try {" in extension
    assert 'error.message.includes("stale")' in extension


def test_recap_marker_matches_shared_live_activity_widget_and_native_recap_indent() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "createLiveActivityWidget" in extension
    assert "const WIDGET_LEADING_SPACES = 1;" in extension
    assert "leadingSpaces: WIDGET_LEADING_SPACES" in extension
    assert "const prefix = i === 0 ? firstPrefix : indent;" in extension
    assert 'const icon = theme.fg("accent", "✦");' in extension
    assert 'const firstPrefix = `${icon} ${label} `;' in extension
    assert 'const indent = " ".repeat(prefixWidth);' in extension
    assert "renderPiWidgetRow" in extension
    assert "continuation lines align with the first recap character rather than the marker" in (PACKAGE / "features" / "recap.feature").read_text(encoding="utf-8")


def test_environment_overrides_take_precedence_over_saved_config() -> None:
    result = run_typescript(
        f"""
        const {{ readRecapConfig }} = await import("{CONFIG_URI}");
        process.env.PI_RECAP_MODEL = "openai/gpt-4o-mini";
        process.env.PI_RECAP_LANGUAGE = "en";
        const config = readRecapConfig();
        console.log(JSON.stringify({{ provider: config.provider, model: config.model, language: config.language }}));
        """
    )
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini"
    assert result["language"] == "en"


def test_config_parsing_and_model_ref() -> None:
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";

        // Hermetic: reading the developer's own recap.json made this assertion
        // depend on whatever that machine happened to persist.
        const agentDir = fs.mkdtempSync(path.join(os.tmpdir(), "recap-config-"));
        process.env.PI_CODING_AGENT_DIR = agentDir;
        fs.writeFileSync(
          path.join(agentDir, "recap.json"),
          JSON.stringify({{ provider: "openai", model: "gpt-4o-mini", enabled: false, language: "zh" }}),
          "utf-8",
        );

        const {{ readRecapConfig, languageLabel }} = await import("{CONFIG_URI}");
        const {{ parseModelRef, modelRef }} = await import("{PIKIT_URI}");

        const parsed1 = parseModelRef("anthropic/claude-3-5-haiku");
        const parsed2 = parseModelRef("invalid-ref");
        const ref = modelRef({{ provider: "openai", model: "gpt-4o-mini", enabled: true, autoRecap: true, language: "zh" }});
        const config = readRecapConfig();
        const unsetAutoRecap = config.autoRecap === undefined;
        fs.writeFileSync(
          path.join(agentDir, "recap.json"),
          JSON.stringify({{ provider: "openai", model: "gpt-4o-mini", enabled: true, autoRecap: false, language: "auto" }}),
          "utf-8",
        );
        const explicitAutoRecap = readRecapConfig().autoRecap;
        const labelAuto = languageLabel("auto");
        const labelZh = languageLabel("zh");
        const labelEn = languageLabel("en");
        fs.rmSync(agentDir, {{ recursive: true, force: true }});

        console.log(JSON.stringify({{
            parsed1,
            parsed2: parsed2 ?? null,
            ref,
            enabled: config.enabled,
            unsetAutoRecap,
            explicitAutoRecap,
            language: config.language,
            labelAuto,
            labelZh,
            labelEn,
        }}));
        """
    )
    assert result["parsed1"] == {"provider": "anthropic", "model": "claude-3-5-haiku"}
    assert result["parsed2"] is None
    assert result["ref"] == "openai/gpt-4o-mini"
    assert result["enabled"] is False
    # An unset preference must stay unset: that is what lets the cost policy
    # decide, and it must not be silently coerced to a stored boolean.
    assert result["unsetAutoRecap"] is True
    assert result["explicitAutoRecap"] is False
    assert result["language"] == "zh"
    assert "Auto" in result["labelAuto"]
    assert "Chinese" in result["labelZh"]
    assert "English" in result["labelEn"]


def test_extract_last_exchange_logic() -> None:
    result = run_typescript(
        f"""
        import {{ getLastExchange, extractMessageText }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", message: {{ role: "user", content: "hello" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "hi there" }} }},
            {{ type: "message", message: {{ role: "user", content: "fix the login bug" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "I found the issue in auth.ts" }} }},
        ];

        const exchange = getLastExchange(entries);
        console.log(JSON.stringify(exchange));
        """
    )
    assert result["user"] == "fix the login bug"
    assert result["assistant"] == "I found the issue in auth.ts"


def test_extract_last_exchange_without_assistant() -> None:
    result = run_typescript(
        f"""
        import {{ getLastExchange }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", message: {{ role: "user", content: "hello" }} }},
        ];

        const exchange = getLastExchange(entries);
        console.log(JSON.stringify({{ hasExchange: exchange !== undefined }}));
        """
    )
    assert result["hasExchange"] is False


def test_extract_last_complete_exchange_does_not_mismatch_new_request_with_old_answer() -> None:
    result = run_typescript(
        f"""
        import {{ getLastExchange }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", message: {{ role: "user", content: "Q1" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "A1", stopReason: "stop" }} }},
            {{ type: "message", message: {{ role: "user", content: "Q2" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "partial", stopReason: "aborted" }} }},
        ];

        console.log(JSON.stringify(getLastExchange(entries)));
        """
    )
    assert result == {"user": "Q1", "assistant": "A1"}


def test_extract_last_complete_exchange_skips_failed_and_tool_only_answers() -> None:
    result = run_typescript(
        f"""
        import {{ getLastExchange }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", message: {{ role: "user", content: "Q1" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "A1", stopReason: "stop" }} }},
            {{ type: "message", message: {{ role: "user", content: "Q2" }} }},
            {{ type: "message", message: {{ role: "assistant", content: [{{ type: "toolCall", name: "run" }}], stopReason: "toolUse" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "failed", stopReason: "error", errorMessage: "boom" }} }},
        ];

        console.log(JSON.stringify(getLastExchange(entries)));
        """
    )
    assert result == {"user": "Q1", "assistant": "A1"}


def test_extract_last_complete_exchange_keeps_newest_answer_for_same_user() -> None:
    result = run_typescript(
        f"""
        import {{ getLastExchange }} from "{RECAP_URI}";

        const entries = [
            {{ type: "message", message: {{ role: "user", content: "U1" }} }},
            {{ type: "message", message: {{ role: "assistant", content: "A1", stopReason: "stop" }} }},
            {{ type: "custom", customType: "tool_result", data: {{ ok: true }} }},
            {{ type: "message", message: {{ role: "assistant", content: "A2", stopReason: "stop" }} }},
        ];

        console.log(JSON.stringify(getLastExchange(entries)));
        """
    )
    assert result == {"user": "U1", "assistant": "A2"}


def test_extract_message_text_string_and_array() -> None:
    result = run_typescript(
        f"""
        import {{ extractMessageText }} from "{RECAP_URI}";

        const t1 = extractMessageText({{ type: "message", message: {{ role: "user", content: "hello world" }} }});
        const t2 = extractMessageText({{ type: "message", message: {{ role: "assistant", content: [{{ type: "text", text: "answer part" }}] }} }});

        console.log(JSON.stringify({{ t1, t2 }}));
        """
    )
    assert result["t1"] == "hello world"
    assert result["t2"] == "answer part"


def test_all_prompt_and_ui_strings_are_english() -> None:
    """All prompts and UI strings in the package source must be English — no CJK."""
    cjk = [
        "\\u4e00-\\u9fff",
        "\\u3000-\\u303f",
        "\\uff00-\\uffef",
    ]
    import re

    pattern = re.compile("[" + "".join(cjk) + "]")
    offenders: list[str] = []
    for path in sorted(EXTENSIONS.glob("*.ts")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "Non-English (CJK) text found in extensions:\n" + "\n".join(offenders)


def test_generate_recap_settles_when_credential_lookup_never_returns() -> None:
    """The wall-clock budget must cover the whole request, credentials included.

    The deadline used to be armed only after the provider call, so a credential
    lookup that never returned left the caller awaiting a recap forever: the
    `/recap now` handler never resolved, the `Recapping...` row stayed mounted,
    and the first-prompt refresh chain never ran again in that session.
    """
    result = run_typescript(
        f"""
        import {{ generateRecap }} from "{RECAP_URI}";

        let completeCalls = 0;
        const started = Date.now();
        const recap = await generateRecap(
          {{
            getApiKeyAndHeaders: () => new Promise(() => {{}}),
            complete: async () => {{ completeCalls++; return {{ role: "assistant", content: [] }}; }},
          }},
          {{ provider: "mock", id: "m1" }},
          "u",
          "a",
          undefined,
          "auto",
          undefined,
          60,
        );

        console.log(JSON.stringify({{ recap, completeCalls, elapsedUnderOneSecond: Date.now() - started < 1000 }}));
        """
    )
    assert result == {"recap": "", "completeCalls": 0, "elapsedUnderOneSecond": True}


def test_generate_recap_settles_when_provider_ignores_cancellation() -> None:
    """An uncooperative provider must not be able to hang the caller either."""
    result = run_typescript(
        f"""
        import {{ generateRecap }} from "{RECAP_URI}";

        const controller = new AbortController();
        const pending = generateRecap(
          {{
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: () => new Promise(() => {{}}),
          }},
          {{ provider: "mock", id: "m1" }},
          "u",
          "a",
          undefined,
          "auto",
          controller.signal,
          60,
        );
        await new Promise((resolve) => setTimeout(resolve, 20));
        controller.abort();
        const recap = await Promise.race([
          pending,
          new Promise((resolve) => setTimeout(() => resolve("still-pending"), 500)),
        ]);

        console.log(JSON.stringify({{ recap }}));
        """
    )
    assert result == {"recap": ""}


def test_widget_refresh_failure_never_rejects_a_completed_recap() -> None:
    """`performRecap` refreshes the widget from a finally block.

    Rethrowing a non-stale widget error there reported generation failure for a
    recap that was already generated and persisted, so `/recap now` rejected.
    """
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredCommand;
        let completeCalls = 0;
        const notices = [];
        const appended = [];
        initExtension({{
          on() {{}},
          registerCommand(_name, command) {{ registeredCommand = command; }},
          appendEntry(customType, data) {{ appended.push({{ customType, recap: data.recap }}); }},
        }});

        const fakeCtx = {{
          mode: "tui",
          hasUI: true,
          cwd: "/tmp/fake-cwd",
          sessionManager: {{
            getBranch: () => [
              {{ type: "message", message: {{ role: "user", content: "fix bug" }} }},
              {{ type: "message", message: {{ role: "assistant", content: "bug fixed in auth.ts" }} }},
            ],
            getSessionFile: () => undefined,
          }},
          ui: {{
            setWidget: () => {{
              if (completeCalls > 0) throw new Error("renderer exploded");
            }},
            notify: (message, level) => notices.push({{ message, level }}),
          }},
          modelRegistry: {{
            find: () => undefined,
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: "Fixed auth bug in auth.ts" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        let outcome = "resolved";
        await registeredCommand.handler("now", fakeCtx).catch((error) => {{
          outcome = `rejected:${{error.message}}`;
        }});

        console.log(JSON.stringify({{
          outcome,
          completeCalls,
          persisted: appended.some((entry) => entry.recap === "Fixed auth bug in auth.ts"),
          warned: notices.some((notice) => notice.message.includes("Recap widget refresh failed") && notice.level === "warning"),
        }}));
        """
    )
    assert result["outcome"] == "resolved"
    assert result["completeCalls"] == 1
    assert result["persisted"] is True
    assert result["warned"] is True


def test_uninformative_output_gate_covers_chinese_recaps() -> None:
    """The gate must reject a bare verb-plus-name in every configured language.

    Its identifier was ASCII-only, so the retry loop it exists for never fired on
    the package's Chinese output: `修复登录` passed while `Fixed` was rejected.
    """
    result = run_typescript(
        f"""
        import {{ isInformativeRecap }} from "{RECAP_URI}";

        console.log(JSON.stringify({{
          zhBare: isInformativeRecap("修复登录"),
          zhVerbOnly: isInformativeRecap("修正"),
          zhColoned: isInformativeRecap("更新："),
          zhSpecific: isInformativeRecap("修复登录重定向问题，auth.ts 补齐回跳测试"),
          enBare: isInformativeRecap("Fixed"),
          enSpecific: isInformativeRecap("Fixed the auth redirect in auth.ts"),
        }}));
        """
    )
    assert result["zhBare"] is False
    assert result["zhVerbOnly"] is False
    assert result["zhColoned"] is False
    assert result["zhSpecific"] is True
    assert result["enBare"] is False
    assert result["enSpecific"] is True


def test_clean_recap_text_never_splits_a_grapheme_or_a_code_span() -> None:
    """The 120 limit must not corrupt the text it truncates.

    `slice(0, 120)` counted UTF-16 units, so a cut through an astral character
    left a lone surrogate in the recap line, and a cut inside an inline code span
    left the odd backtick the package otherwise works to preserve balanced.
    """
    result = run_typescript(
        f"""
        import {{ cleanRecapText }} from "{RECAP_URI}";

        const rockets = cleanRecapText("\\u{{1F680}}".repeat(130));
        const flags = cleanRecapText("\\u{{1F1E8}}\\u{{1F1F3}}".repeat(130));
        const codeCut = cleanRecapText("x".repeat(112) + "`inner span of text` tail");
        const completeSpan = cleanRecapText("`list_directory_sessions` aligned the monitor row");

        console.log(JSON.stringify({{
          rocketGraphemes: Array.from(rockets).length,
          rocketLoneSurrogate: /[\\uD800-\\uDBFF](?![\\uDC00-\\uDFFF])|(?<![\\uD800-\\uDBFF])[\\uDC00-\\uDFFF]/.test(rockets),
          flagLoneSurrogate: /[\\uD800-\\uDBFF](?![\\uDC00-\\uDFFF])|(?<![\\uD800-\\uDBFF])[\\uDC00-\\uDFFF]/.test(flags),
          codeCutBackticks: codeCut.split("`").length - 1,
          codeCutLength: codeCut.length,
          completeSpan,
        }}));
        """
    )
    assert result["rocketGraphemes"] == 120
    assert result["rocketLoneSurrogate"] is False
    assert result["flagLoneSurrogate"] is False
    assert result["codeCutBackticks"] == 0
    assert result["codeCutLength"] <= 120
    assert result["completeSpan"].startswith("`list_directory_sessions`")


def test_completed_recap_is_reused_only_while_it_is_the_displayed_one() -> None:
    """A stored result must not answer for a recap it was not produced from.

    The previous recap belongs to the prompt, so a result generated against an
    older recap is the wrong answer for a replaced one. The invariant is carried
    by the produced text instead of by the request key: keying on the previous
    recap would defeat deduplication outright, because every generation changes
    the previous recap of the next request for the same exchange.
    """
    result = run_typescript(
        f"""
        // Loaded dynamically: config.ts resolves its path when it loads, so a
        // hoisted static import would read the real agent directory.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let completeCalls = 0;
        const branch = [
          {{ type: "message", message: {{ role: "user", content: "add tests" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "auth tests added" }} }},
        ];
        initExtension({{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand() {{}},
          appendEntry() {{}},
        }});
        const fakeCtx = {{
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => branch, getSessionFile: () => undefined }},
          ui: {{ setWidget: () => {{}}, notify: () => {{}} }},
          modelRegistry: {{
            find: () => undefined,
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: `Recap number ${{completeCalls}}` }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "m1" }},
        }};

        await registeredEvents["session_start"]({{}}, fakeCtx);
        registeredEvents["input"]({{ source: "interactive", text: "add tests" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 40));
        const afterFirstSettle = completeCalls;

        // Same exchange again, nothing else changed: the recap on screen is still
        // the one that request produced, so it is reused.
        registeredEvents["input"]({{ source: "interactive", text: "add tests" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 40));
        const afterRepeatedSettle = completeCalls;

        // A session replacement restores a different recap for the same exchange.
        // Restore books the restored text as the product of its request, so
        // startup suppression still holds and the stored result is not reused.
        await registeredEvents["session_start"]({{}}, {{
          ...fakeCtx,
          sessionManager: {{
            getBranch: () => [
              ...branch,
              {{ type: "custom", customType: "recap", data: {{ recap: "Restored recap" }} }},
            ],
            getSessionFile: () => undefined,
          }},
        }});
        registeredEvents["input"]({{ source: "interactive", text: "add tests" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 40));
        const afterRestoreSettle = completeCalls;

        console.log(JSON.stringify({{
          afterFirstSettle,
          afterRepeatedSettle,
          afterRestoreSettle,
        }}));
        """
    )
    assert result["afterFirstSettle"] == 1
    assert result["afterRepeatedSettle"] == 1
    assert result["afterRestoreSettle"] == 1
    # The reuse condition is the encoded invariant, not just an accident of the
    # paths that set both fields together today.
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "completedRequestRecap === currentRecap" in extension
    assert "completedRequestRecap = savedRecap;" in extension
    assert "completedRequestRecap = text;" in extension


def test_automatic_recap_is_withheld_from_reasoning_models_by_default() -> None:
    """Automatic recapping must not spend a reasoning model on every turn.

    It used to run once per settled turn on the session's own model, with no
    metering and no bound: a reasoning model burns its thinking budget before any
    recap text exists, competing with the turn that paid for it. Manual
    generation and the restored recap line stay available.
    """
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";

        // `/recap auto` persists the preference, so keep it out of the real
        // agent directory.
        const agentDir = fs.mkdtempSync(path.join(os.tmpdir(), "recap-auto-optin-"));
        process.env.PI_CODING_AGENT_DIR = agentDir;

        const {{ resolveAutoRecap }} = await import("{RECAP_URI}");

        const matrix = {{
          reasoningNoOverride: resolveAutoRecap(undefined, {{ reasoning: true }}, false),
          reasoningWithOverride: resolveAutoRecap(undefined, {{ reasoning: true }}, true),
          plainNoOverride: resolveAutoRecap(undefined, {{ reasoning: false }}, false),
          explicitOn: resolveAutoRecap(true, {{ reasoning: true }}, false),
          explicitOff: resolveAutoRecap(false, {{ reasoning: false }}, true),
          noModel: resolveAutoRecap(undefined, undefined, false),
        }};

        // Loaded after the agent dir override: config.ts resolves its path at
        // import time, so a hoisted static import would write the real one.
        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let command;
        let completeCalls = 0;
        const notices = [];
        let branch = [
          {{ type: "message", message: {{ role: "user", content: "add tests" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "auth tests added" }} }},
        ];
        initExtension({{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand(_name, definition) {{ command = definition; }},
          appendEntry() {{}},
        }});
        const fakeCtx = {{
          mode: "tui",
          hasUI: true,
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => branch, getSessionFile: () => undefined }},
          ui: {{ setWidget: () => {{}}, notify: (message) => notices.push(message) }},
          modelRegistry: {{
            find: () => undefined,
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => {{
              completeCalls++;
              return {{ role: "assistant", content: [{{ type: "text", text: "Added auth tests" }}] }};
            }},
          }},
          model: {{ provider: "mock", id: "reasoner", reasoning: true }},
        }};

        // Startup computes a recap for a session that has none; that one call is
        // not per-turn cost, so the counter starts after it.
        await registeredEvents["session_start"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 40));
        const startupCalls = completeCalls;
        completeCalls = 0;

        registeredEvents["input"]({{ source: "interactive", text: "add tests" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 40));
        const settledCalls = completeCalls;

        // Manual generation is never withheld.
        await command.handler("now", fakeCtx);
        const afterManualCalls = completeCalls;

        // Opting in explicitly turns the automatic path back on, and the new
        // exchange is one the model has not summarized yet.
        await command.handler("auto", fakeCtx);
        branch = [
          ...branch,
          {{ type: "message", message: {{ role: "user", content: "add more tests" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "boundary tests added" }} }},
        ];
        registeredEvents["input"]({{ source: "interactive", text: "add more tests" }}, fakeCtx);
        await registeredEvents["agent_settled"]({{}}, fakeCtx);
        await new Promise((resolve) => setTimeout(resolve, 40));
        const persistedPreference = JSON.parse(
          fs.readFileSync(path.join(agentDir, "recap.json"), "utf-8"),
        ).autoRecap;
        fs.rmSync(agentDir, {{ recursive: true, force: true }});

        console.log(JSON.stringify({{
          matrix,
          persistedPreference,
          startupCalls,
          settledCalls,
          afterManualCalls,
          afterOptInCalls: completeCalls,
          autoNotice: notices.find((message) => message.startsWith("Auto-recap:")),
        }}));
        """
    )
    assert result["matrix"]["reasoningNoOverride"]["enabled"] is False
    assert result["matrix"]["reasoningNoOverride"]["reason"]
    assert result["matrix"]["reasoningWithOverride"] == {"enabled": True}
    assert result["matrix"]["plainNoOverride"] == {"enabled": True}
    assert result["matrix"]["explicitOn"] == {"enabled": True}
    assert result["matrix"]["explicitOff"] == {"enabled": False}
    assert result["matrix"]["noModel"] == {"enabled": True}
    assert result["startupCalls"] == 1
    assert result["settledCalls"] == 0
    assert result["afterManualCalls"] == 1
    assert result["afterOptInCalls"] == 2
    assert result["persistedPreference"] is True
    assert result["autoNotice"] == "Auto-recap: on"


def test_automatic_recap_policy_is_reported_in_the_management_surfaces() -> None:
    """A policy-suppressed auto-recap must be discoverable, not silent."""
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";

        const agentDir = fs.mkdtempSync(path.join(os.tmpdir(), "recap-auto-policy-"));
        process.env.PI_CODING_AGENT_DIR = agentDir;

        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let command;
        initExtension({{ on() {{}}, registerCommand(_name, definition) {{ command = definition; }}, appendEntry() {{}} }});

        const notices = [];
        let titles = [];
        const fakeCtx = {{
          hasUI: false,
          mode: "tui",
          cwd: "/tmp/fake-cwd",
          sessionManager: {{ getBranch: () => [], getSessionFile: () => undefined }},
          scopedModels: [],
          modelRegistry: {{ getAll: () => [], getAvailable: () => [], find: () => undefined }},
          model: {{ provider: "mock", id: "reasoner", reasoning: true }},
          ui: {{ notify: (message) => notices.push(message), select: async () => undefined, setWidget: () => {{}} }},
        }};
        await command.handler("", fakeCtx);
        const summary = notices.at(-1);

        const menuCtx = {{ ...fakeCtx, hasUI: true, ui: {{ ...fakeCtx.ui, select: async (title) => {{ titles.push(title); return undefined; }} }} }};
        await command.handler("", menuCtx);
        const menuTitle = titles.at(-1);
        fs.rmSync(agentDir, {{ recursive: true, force: true }});

        console.log(JSON.stringify({{ summary, menuTitle }}));
        """
    )
    assert "Auto-recap: off" in result["summary"]
    assert "reasoning models" in result["summary"]
    assert "Auto: off" in result["menuTitle"]
    assert "reasoning models" in result["menuTitle"]


def test_directory_recap_sync_follows_the_agent_dir_and_leaves_activity_fields_alone() -> None:
    """One registry path, one ownership check, and one owner per field.

    The path used to be spelled from the home directory while the package's own
    config honoured `PI_CODING_AGENT_DIR`, so a sandboxed agent directory still
    wrote to the real registry. The sync also stamped `updatedAt`, a field the
    session-activity writers own, which reordered their recency and liveness
    views for a turn that changed nothing but its summary.
    """
    result = run_typescript(
        f"""
        import * as fs from "node:fs";
        import * as os from "node:os";
        import * as path from "node:path";

        const root = fs.mkdtempSync(path.join(os.tmpdir(), "recap-registry-"));
        const agentDir = path.join(root, "agent");
        const cwd = path.join(root, "project");
        fs.mkdirSync(agentDir, {{ recursive: true }});
        fs.mkdirSync(cwd, {{ recursive: true }});
        process.env.PI_CODING_AGENT_DIR = agentDir;

        const {{ directorySessionsDir, getDirectorySessionKey }} = await import("{PIKIT_URI}");
        const recordPath = path.join(directorySessionsDir(), getDirectorySessionKey(cwd), "session-1.json");
        fs.mkdirSync(path.dirname(recordPath), {{ recursive: true }});
        fs.writeFileSync(
          recordPath,
          JSON.stringify({{ cwd, pid: 42, status: "active", updatedAt: 1000, recap: "Restored from registry" }}),
          "utf-8",
        );

        const extensionModule = await import("{INDEX_URI}");
        const moduleValue = extensionModule.default ?? extensionModule;
        const initExtension = typeof moduleValue === "function" ? moduleValue : moduleValue.default;

        let registeredEvents = {{}};
        let command;
        let branch = [];
        const widgets = [];
        initExtension({{
          on(event, handler) {{ registeredEvents[event] = handler; }},
          registerCommand(_name, definition) {{ command = definition; }},
          appendEntry() {{}},
        }});
        const fakeCtx = {{
          mode: "tui",
          hasUI: true,
          cwd,
          sessionManager: {{
            getBranch: () => branch,
            getSessionFile: () => path.join(root, "session-1.jsonl"),
          }},
          ui: {{ setWidget: (name, factory) => widgets.push({{ name, factory }}), notify: () => {{}} }},
          modelRegistry: {{
            find: () => undefined,
            getApiKeyAndHeaders: async () => ({{ ok: true, apiKey: "k", headers: {{}} }}),
            complete: async () => ({{ role: "assistant", content: [{{ type: "text", text: "Added auth tests" }}] }}),
          }},
          model: {{ provider: "mock", id: "m1", reasoning: false }},
        }};

        await registeredEvents["session_start"]({{}}, fakeCtx);
        const recapWidget = widgets.filter((call) => call.name === "recap").at(-1);
        const restoredLines = recapWidget?.factory
          ? recapWidget.factory({{ requestRender: () => {{}} }}, {{ fg: (_name, text) => text }}).render(80)
          : [];

        branch = [
          {{ type: "message", message: {{ role: "user", content: "add tests" }} }},
          {{ type: "message", message: {{ role: "assistant", content: "auth tests added" }} }},
        ];
        await command.handler("now", fakeCtx);
        const record = JSON.parse(fs.readFileSync(recordPath, "utf-8"));
        fs.rmSync(root, {{ recursive: true, force: true }});

        console.log(JSON.stringify({{
          restored: restoredLines.some((line) => line.includes("Restored from registry")),
          recap: record.recap,
          updatedAt: record.updatedAt,
          pid: record.pid,
        }}));
        """
    )
    assert result["restored"] is True
    assert result["recap"] == "Added auth tests"
    assert result["updatedAt"] == 1000
    assert result["pid"] == 42


def test_recap_prompt_rules_stay_bounded() -> None:
    """Prompt rules must not regrow into near-duplicate lines.

    Fifteen rules cost every recap, and four of them restated one requirement:
    report only what the exchange evidences, treat requests as intent, do not
    claim unevidenced work, and do not treat a referenced path as an inspected
    file. The repeated wording outweighed the rule that actually applied.
    """
    result = run_typescript(
        f"""
        import {{ buildRecapPrompt }} from "{RECAP_URI}";

        const withOutcome = buildRecapPrompt("u", "a");
        const withoutOutcome = buildRecapPrompt("u", "");
        const countRules = (prompt) => prompt
          .split("Rules:\\n")[1]
          .split("\\n\\n")[0]
          .split("\\n")
          .filter((line) => line.startsWith("- ")).length;

        console.log(JSON.stringify({{
          withOutcome: countRules(withOutcome),
          withoutOutcome: countRules(withoutOutcome),
          rulesAreSingleLines: !withOutcome.includes("\\n- Single line"),
        }}));
        """
    )
    assert result["withOutcome"] <= 8
    assert result["withoutOutcome"] <= 8
    assert result["rulesAreSingleLines"] is True
