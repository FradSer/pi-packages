from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
EXTENSIONS = PACKAGE / "extensions"
RECAP_URI = (EXTENSIONS / "recap.ts").as_uri()
INDEX_URI = (EXTENSIONS / "index.ts").as_uri()
CONFIG_URI = (EXTENSIONS / "config.ts").as_uri()
PIKIT_URI = (REPO / "packages" / "pi-kit" / "src" / "index.ts").as_uri()


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
    assert "Scenario: Recap widget is displayed above the editor by default" in feature
    assert "Scenario: Recap is informative and scannable" in feature
    assert "Scenario: Recap reflects only evidenced progress" in feature
    assert "Scenario: /recap opens an interactive management menu" in feature
    assert "Scenario: Generate recap now bypasses same-exchange deduplication" in feature
    assert "Scenario: Model selection supports custom provider and model overrides" in feature
    assert "Scenario: Language selection allows specifying target generation language" in feature
    assert "Scenario: Recap shows a generation marker while refreshing" in feature
    assert "Scenario: Recap preserves a leading inline code marker" in feature
    assert "Scenario: Recap maintains context continuity using previous recap and last exchange" in feature
    assert "Scenario: Generated recap is persisted to the session" in feature
    assert "Scenario: Existing session restores persisted recap on startup across restarts" in feature
    assert "Scenario: Session replacement cancels a pending first-prompt recap" in feature
    assert "Scenario: Existing session without saved recap computes initial recap on startup" in feature
    assert "Scenario: Existing recap prevents redundant startup generation" in feature
    assert "Scenario: Headless recap commands do not start generation" in feature
    assert "Scenario: Background recap ignores stale session context failures" in feature
    assert "Scenario: Recap generation requests are deduplicated and cancellable" in feature
    assert "Scenario: Recap generation times out safely" in feature
    assert "Scenario: Recap ignores thinking-only provider output" in feature
    assert "Scenario: Recap skips unchanged persistence" in feature


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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

        let registeredEvents = {{}};
        let completeCalls = 0;
        let promptTexts = [];
        let appendedEntries = [];
        let resolveInitial;
        const initialCompletion = new Promise((resolve) => {{ resolveInitial = resolve; }});
        let branch = [];
        let setWidgetCall;
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
            setWidget: (name, factory) => {{ setWidgetCall = {{ name, factory }}; }},
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
        const pendingWidget = setWidgetCall?.factory(
          {{ requestRender: () => {{}} }},
          {{ fg: (_name, text) => text }},
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


def test_session_replacement_aborts_pending_first_prompt_recap() -> None:
    result = run_typescript(
        f"""
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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


def test_startup_does_not_regenerate_when_saved_recap_exists() -> None:
    result = run_typescript(
        f"""
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;
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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;
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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        import extensionModule from "{INDEX_URI}";
        const initExtension = typeof extensionModule === "function" ? extensionModule : extensionModule.default;

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
        }}));
        """
    )
    assert result["widgetSet"] is True
    assert result["widgetName"] == "recap"
    assert any("Persisted: Fixed auth bug in auth.ts" in line for line in result["lines"])

    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert (PACKAGE / "index.ts").is_file()


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
    assert "PI_SPINNER_FRAMES" in extension
    assert "PI_SPINNER_FRAMES[recapSpinnerFrame]" in extension
    assert "requestRender" in extension
    assert "generatingRecap" in extension
    assert "same visual column as the native working spinner" in (PACKAGE / "features" / "recap.feature").read_text(encoding="utf-8")


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
    assert "maxTokens: 96" in recap
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
    assert "wrapTextWithAnsi" in extension


def test_headless_sessions_skip_recap_widget_and_generation() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "if (ctx.mode !== \"tui\") return;" in extension
    assert 'if (ctx.mode === "tui" && config.enabled && !savedRecap)' in extension
    assert 'if (ctx.mode !== "tui" || !config.enabled || !config.autoRecap)' in extension


def test_widget_refresh_ignores_disposed_context() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert "function updateRecapWidget(ctx: ExtensionContext): void" in extension
    assert "try {" in extension
    assert 'error.message.includes("stale")' in extension


def test_recap_marker_matches_native_working_spinner_indent() -> None:
    extension = (EXTENSIONS / "index.ts").read_text(encoding="utf-8")
    assert 'lines.push(` ${theme.fg("accent", `${spinner} Recapping...`)}`);' in extension
    assert "const prefix = i === 0 ? firstPrefix : indent;" in extension
    assert 'const icon = theme.fg("accent", "✦");' in extension
    assert 'const firstPrefix = ` ${icon} ${label} `;' in extension
    assert 'const indent = " ".repeat(prefixWidth);' in extension
    assert "wrapTextWithAnsi(currentRecap, contentWidth)" in extension
    assert "continuation lines align with the first recap character rather than the marker" in (PACKAGE / "features" / "recap.feature").read_text(encoding="utf-8")


def test_environment_overrides_take_precedence_over_saved_config() -> None:
    result = run_typescript(
        f"""
        import {{ readRecapConfig }} from "{CONFIG_URI}";
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
        import {{ readRecapConfig, languageLabel }} from "{CONFIG_URI}";
        import {{ parseModelRef, modelRef }} from "{PIKIT_URI}";

        const parsed1 = parseModelRef("anthropic/claude-3-5-haiku");
        const parsed2 = parseModelRef("invalid-ref");
        const ref = modelRef({{ provider: "openai", model: "gpt-4o-mini", enabled: true, autoRecap: true, language: "zh" }});
        const config = readRecapConfig();
        const labelAuto = languageLabel("auto");
        const labelZh = languageLabel("zh");
        const labelEn = languageLabel("en");

        console.log(JSON.stringify({{
            parsed1,
            parsed2: parsed2 ?? null,
            ref,
            enabled: config.enabled,
            autoRecap: config.autoRecap,
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
    assert isinstance(result["enabled"], bool)
    assert isinstance(result["autoRecap"], bool)
    assert isinstance(result["language"], str)
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


def test_readme_documents_features() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "/recap" in readme
    assert "aboveEditor" in readme or "widget" in readme
    assert "Model Selection" in readme or "recap.json" in readme
    assert "Non-blocking" in readme or "in-process" in readme


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
