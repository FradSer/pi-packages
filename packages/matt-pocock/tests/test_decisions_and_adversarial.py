from __future__ import annotations



# ── test_decision_adapters.py ──
"""Both UI adapters execute the same decision contract through the registered tool."""

import sys
from pathlib import Path

import pytest

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


@pytest.mark.parametrize("native", [False, pytest.param(True, marks=pytest.mark.skipif(sys.platform != "darwin", reason="macOS adapter"))])
def test_question_outcomes_match_across_ui_adapters(tmp_path: Path, native: bool) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"useNativeDialog": true}')
    binary = tmp_path / "osascript"
    binary.write_text('''#!/usr/bin/env node
const mode = process.env.MP_TEST_DECISION;
if (mode === "failure") process.exit(1);
const input = process.argv.at(-1).includes("displayDialog");
const result = input
  ? { buttonReturned: "Select", textReturned: mode === "blank" ? "" : "custom answer" }
  : mode === "cancel" ? false : [mode === "custom" || mode === "blank" ? "Type custom answer..." : "A"];
console.log(JSON.stringify(result));
''')
    binary.chmod(0o755)
    result = run_typescript(RUNTIME_HARNESS + f'''
        process.env.PATH = {str(tmp_path)!r} + ":" + process.env.PATH;
        process.env.PI_MATT_POCOCK_CONFIG_FILE = {str(config)!r};
        process.env.PI_NO_NATIVE_DIALOG = {"'0'" if native else "'1'"};
        for (const name of ["CI", "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"]) delete process.env[name];
        const r = runtime(); await r.start(); const results = {{}}; let fallbackCalls = 0;
        for (const mode of ["selected", "cancel", "custom", "blank", "failure"]) {{
          process.env.MP_TEST_DECISION = mode;
          r.ctx.ui.select = async () => {{
            fallbackCalls++;
            return mode === "cancel" ? undefined : mode === "custom" || mode === "blank" ? "Type custom answer..." : mode === "failure" ? "B" : "A";
          }};
          r.ctx.ui.input = async () => mode === "blank" ? "" : "custom answer";
          results[mode] = await r.call("matt_pocock_ask", {{ question: "Scope?", options: ["A", "B"], recommended: "A" }});
        }}
        console.log(JSON.stringify({{ results, fallbackCalls }}));
    ''')
    outcomes = result["results"]
    assert outcomes["selected"]["details"] == {"answer": "A", "is_custom": False, "source": "choice_selected"}
    assert outcomes["cancel"]["details"] == {"pending": True, "timed_out": False, "source": "cancelled"}
    assert outcomes["custom"]["details"] == {"answer": "custom answer", "is_custom": True, "source": "custom_input"}
    assert outcomes["blank"]["details"] == {"pending": True, "source": "custom_input_cancelled"}
    assert outcomes["failure"]["details"]["answer"] == "B"
    assert result["fallbackCalls"] == (1 if native else 5)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS adapter")
def test_native_deadline_adopts_the_recommendation_without_a_fallback(tmp_path: Path) -> None:
    """Both native dialogs report their own expiry, and the ask adopts the recommendation."""
    config = tmp_path / "config.json"
    config.write_text('{"useNativeDialog": true}')
    binary = tmp_path / "osascript"
    binary.write_text('''#!/usr/bin/env node
const mode = process.env.MP_TEST_NATIVE_DEADLINE;
if (process.argv.at(-1).includes("displayDialog")) {
  console.log(JSON.stringify({ gaveUp: true }));
  process.exit(0);
}
if (mode === "hang") { setTimeout(() => {}, 5000); return; }
console.log(JSON.stringify(["Type custom answer..."]));
''')
    binary.chmod(0o755)
    result = run_typescript(RUNTIME_HARNESS + f'''
        process.env.PATH = {str(tmp_path)!r} + ":" + process.env.PATH;
        process.env.PI_MATT_POCOCK_CONFIG_FILE = {str(config)!r};
        process.env.PI_NO_NATIVE_DIALOG = "0";
        for (const name of ["CI", "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"]) delete process.env[name];
        const r = runtime(); await r.start(); const results = {{}}; let fallbackCalls = 0;
        r.ctx.ui.select = async () => {{ fallbackCalls++; return undefined; }};
        r.ctx.ui.input = async () => {{ fallbackCalls++; return undefined; }};
        const question = {{ question: "Scope?", options: ["A", "B"], recommended: "B" }};
        process.env.MP_TEST_NATIVE_DEADLINE = "custom";
        results.customExpiry = await r.call("matt_pocock_ask", {{ ...question, timeout_seconds: 30 }});
        process.env.MP_TEST_NATIVE_DEADLINE = "hang";
        results.selectorExpiry = await r.call("matt_pocock_ask", {{ ...question, timeout_seconds: 0.05 }});
        console.log(JSON.stringify({{ results, fallbackCalls }}));
    ''')
    assert result["fallbackCalls"] == 0
    for name in ("customExpiry", "selectorExpiry"):
        assert result["results"][name]["details"] == {
            "answer": "B", "is_custom": False, "timed_out": True,
            "pending": False, "source": "timeout_recommended",
        }


# ── test_adversarial_decisions.py ──
"""Adversarial boundaries for the Pi v1 decision and native dialog adapters."""

from pathlib import Path

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


FAKE_OSASCRIPT = r'''#!/usr/bin/env node
const fs = require("node:fs");
const mode = process.env.MP_NATIVE_MODE;
const marker = process.env.MP_NATIVE_MARKER;
const script = process.argv.at(-1) ?? "";
const mark = (value) => marker && fs.appendFileSync(marker, value);
mark("start");
if (mode === "delayed") {
  process.on("SIGTERM", () => { mark("term"); process.exit(143); });
  setTimeout(() => console.log(script.includes("displayDialog")
    ? JSON.stringify({ buttonReturned: "OK", textReturned: "done" })
    : JSON.stringify(["A"])), 1000);
} else if (mode === "malformed") {
  console.log("not-json");
} else if (mode === "null") {
  console.log("null");
} else if (mode === "other-button") {
  console.log(JSON.stringify({ buttonReturned: "OTHER" }));
} else if (mode === "missing-button") {
  console.log(JSON.stringify({ textReturned: "done" }));
} else if (mode === "bad-text") {
  console.log(JSON.stringify({ buttonReturned: "OK", textReturned: 42 }));
} else if (mode === "multi") {
  console.log(JSON.stringify(["A", "B"]));
} else if (mode === "cancel-error") {
  process.stderr.write("User canceled.\n");
  process.exit(1);
} else if (mode === "failure") {
  process.stderr.write("permission denied\n");
  process.exit(1);
} else {
  console.log(script.includes("displayDialog")
    ? JSON.stringify({ buttonReturned: "OK", textReturned: "done" })
    : JSON.stringify(["A"]));
}
'''


def native_harness(tmp_path: Path, body: str) -> dict[str, object]:
    binary = tmp_path / "osascript"
    binary.write_text(FAKE_OSASCRIPT)
    binary.chmod(0o755)
    marker = tmp_path / "native.marker"
    return run_typescript(
        f'''
        import {{ macosChooseFromList, macosInputDialog, isNativeDialogSupported, loadConfig }} from "./packages/matt-pocock/src/native-dialog.ts";
        process.env.PATH = {str(tmp_path)!r} + ":" + process.env.PATH;
        process.env.MP_NATIVE_MARKER = {str(marker)!r};
        const env = {{ platform: "darwin", env: {{}} }};
        {body}
        '''
    )


def test_native_abort_before_and_after_spawn_are_cancelled_and_reaped(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        '''
        process.env.MP_NATIVE_MODE = "delayed";
        const before = new AbortController(); before.abort();
        const immediate = await macosChooseFromList({ prompt: "q", items: ["A"], signal: before.signal }, env);
        const after = new AbortController();
        const pending = macosChooseFromList({ prompt: "q", items: ["A"], signal: after.signal }, env);
        const fs = await import("node:fs/promises");
        let ready = false;
        for (let attempt = 0; attempt < 500; attempt++) {
          if ((await fs.readFile(process.env.MP_NATIVE_MARKER, "utf8").catch(() => "")).includes("start")) {
            ready = true;
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 10));
        }
        if (!ready) throw new Error("fake osascript did not reach the ready marker before the abort deadline");
        after.abort();
        const late = await pending;
        await new Promise((resolve) => setTimeout(resolve, 300));
        const marker = (await import("node:fs/promises")).readFile(process.env.MP_NATIVE_MARKER, "utf8").catch(() => "");
        console.log(JSON.stringify({ immediate, late, marker: await marker }));
        ''',
    )
    assert result["immediate"] == {"action": "cancelled"}
    assert result["late"] == {"action": "cancelled"}
    assert result["marker"] == "startterm"


def test_native_malformed_jxa_output_is_a_controlled_error(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        '''
        const errors = {};
        for (const mode of ["malformed", "null", "other-button", "missing-button", "bad-text"]) {
          process.env.MP_NATIVE_MODE = mode;
          try { await macosInputDialog({ prompt: "q" }, env); }
          catch (value) { errors[mode] = String(value); }
        }
        console.log(JSON.stringify({ errors }));
        ''',
    )
    assert set(result["errors"]) == {"malformed", "null", "other-button", "missing-button", "bad-text"}
    assert all("Invalid native input result" in error for error in result["errors"].values())


def test_native_timeout_rejects_node_timer_overflow_and_list_is_single_select(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        '''
        process.env.MP_NATIVE_MODE = "delayed";
        let hugeError = "";
        try { await macosInputDialog({ prompt: "q", timeoutSeconds: 2147484 }, env); }
        catch (value) { hugeError = String(value); }
        const hugeMarker = (await import("node:fs/promises")).readFile(process.env.MP_NATIVE_MARKER, "utf8").catch(() => "");
        process.env.MP_NATIVE_MODE = "multi";
        let listError = "";
        try { await macosChooseFromList({ prompt: "q", items: ["A", "B"] }, env); }
        catch (value) { listError = String(value); }
        console.log(JSON.stringify({ hugeError, hugeMarker: await hugeMarker, listError }));
        ''',
    )
    assert "timeout" in result["hugeError"].lower()
    assert result["hugeMarker"] == ""
    assert "Invalid native selection result" in result["listError"]


def test_question_literal_custom_option_and_whitespace_recommendation_are_preserved() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        const r = runtime(); await r.start();
        r.ctx.ui.select = async () => "Type custom answer...";
        r.ctx.ui.input = async () => "must not be requested";
        const collision = await r.call("matt_pocock_ask", {
          question: "Pick one", options: ["Type custom answer...", "B"], recommended: "B", allow_custom: true,
        });
        r.ctx.ui.select = async () => " A ";
        let whitespaceError = "";
        let whitespace;
        try {
          whitespace = await r.call("matt_pocock_ask", {
            question: "Pick one", options: [" A ", "B"], recommended: " A ", allow_custom: false,
          });
        } catch (value) { whitespaceError = String(value); }
        console.log(JSON.stringify({ collision, whitespace, whitespaceError }));
    ''')
    assert result["collision"]["details"] == {
        "answer": "Type custom answer...", "is_custom": False, "source": "choice_selected",
    }
    assert result["whitespace"]["details"] == {
        "answer": " A ", "is_custom": False, "source": "choice_selected",
    }
    assert result["whitespaceError"] == ""


def test_native_dialog_rejects_invalid_buttons_and_timeout(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        '''
        const errors = [];
        for (const options of [
          { prompt: "q", buttons: ["A", "A"] },
          { prompt: "q", buttons: ["A", "B"], defaultButton: "C" },
          { prompt: "q", buttons: ["A", "B"], cancelButton: "C" },
          { prompt: "q", timeoutSeconds: Infinity },
        ]) {
          try { await macosInputDialog(options, env); }
          catch (value) { errors.push(String(value)); }
        }
        console.log(JSON.stringify({ errors }));
        ''',
    )
    assert len(result["errors"]) == 4
    assert all("native" in error.lower() or "button" in error.lower() or "timeout" in error.lower() for error in result["errors"])


def test_native_cancel_stderr_is_not_a_failure_but_other_stderr_is(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        '''
        process.env.MP_NATIVE_MODE = "cancel-error";
        const cancelled = await macosInputDialog({ prompt: "q" }, env);
        process.env.MP_NATIVE_MODE = "failure";
        let error = "";
        try { await macosInputDialog({ prompt: "q" }, env); }
        catch (value) { error = String(value); }
        console.log(JSON.stringify({ cancelled, error }));
        ''',
    )
    assert result["cancelled"] == {"action": "cancelled"}
    assert "Native dialog process failed" in result["error"]


def test_config_and_environment_guards_are_fail_closed(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        f'''
        const fs = await import("node:fs/promises");
        const invalid = {str(tmp_path / "invalid.json")!r};
        await fs.writeFile(invalid, "{{ broken");
        const config = loadConfig(invalid);
        const supported = isNativeDialogSupported({{ platform: "darwin", env: {{}} }});
        const ci = isNativeDialogSupported({{ platform: "darwin", env: {{ CI: "true" }} }});
        const ssh = isNativeDialogSupported({{ platform: "darwin", env: {{ SSH_TTY: "/dev/pts/1" }} }});
        const linux = isNativeDialogSupported({{ platform: "linux", env: {{}} }});
        console.log(JSON.stringify({{ config, supported, ci, ssh, linux }}));
        ''',
    )
    assert result == {"config": {"useNativeDialog": False}, "supported": True, "ci": False, "ssh": False, "linux": False}


# ── test_adversarial_gateway.py ──
"""Adversarial gateway, command, and in-flight decision contracts.

These cases deliberately exercise the public Pi tool/command seams rather than
calling private workflow helpers.  The bounded races are important: a decision
that is no longer valid must dismiss its adapter, not merely return a pending
result after the user eventually answers.
"""

import pytest

from matt_pocock_helpers import RUNTIME_HARNESS as HARNESS, run_typescript


def test_model_gateway_rejects_user_only_capability_without_writes() -> None:
    """Given a model gateway call, a user-only capability remains untouched."""
    result = run_typescript(HARNESS + """
        const r = runtime(); let error;
        try {
          await r.call("matt_pocock_workflow", {
            mode: "capability", capability: "setup-matt-pocock-skills",
          });
        } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error, entries: r.entries.length, active: r.active(), deliveries: r.deliveries() }));
    """)
    assert "not available to the model gateway" in result.get("error", ""), result
    assert result["entries"] == 0
    assert result["active"] == ["read", "matt_pocock_workflow"]
    assert result["deliveries"] == []


def test_model_gateway_reads_reference_without_invoking_user_only_root() -> None:
    """Given a disclosed reference, reading it does not invoke its user-only root."""
    result = run_typescript(HARNESS + """
        const r = runtime(); let error; let value;
        try {
          value = await r.call("matt_pocock_workflow", {
            mode: "reference", capability: "setup-matt-pocock-skills", reference: "domain",
          });
        } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error, value, entries: r.entries.length, active: r.active(), deliveries: r.deliveries() }));
    """)
    assert "error" not in result, result
    text = result["value"]["content"][0]["text"]
    assert 'source="procedure/domain"' in text
    assert 'source="procedure/setup-matt-pocock-skills"' not in text
    assert result["entries"] == 0
    assert result["active"] == ["read", "matt_pocock_workflow"]
    assert result["deliveries"] == []


def test_repeated_start_reference_and_terminal_operations_are_atomic() -> None:
    """Given one work item, repeats do not append state or revive active tools."""
    result = run_typescript(HARNESS + """
        const r = runtime(); await r.start();
        let duplicateStart; let duplicateReference;
        try { await r.start(); } catch (cause) { duplicateStart = String(cause); }
        await r.call("matt_pocock_active", { action: "load", reference: "improve-codebase-architecture" });
        const beforeDuplicateReference = r.entries.length;
        try {
          await r.call("matt_pocock_active", { action: "load", reference: "improve-codebase-architecture" });
        } catch (cause) { duplicateReference = String(cause); }
        const afterDuplicateReference = r.entries.length;
        await r.call("matt_pocock_active", { action: "complete" });
        let duplicateComplete; let duplicateCancel;
        try { await r.call("matt_pocock_active", { action: "complete" }); } catch (cause) { duplicateComplete = String(cause); }
        try { await r.call("matt_pocock_active", { action: "cancel", reason: "late retry" }); } catch (cause) { duplicateCancel = String(cause); }
        console.log(JSON.stringify({
          duplicateStart, duplicateReference, duplicateComplete, duplicateCancel,
          beforeDuplicateReference, afterDuplicateReference,
          entries: r.entries.length, active: r.active(),
        }));
    """)
    assert "already active" in result["duplicateStart"]
    assert result["beforeDuplicateReference"] == result["afterDuplicateReference"] == 2
    assert result["duplicateReference"]
    assert "No active Matt Pocock workflow" in result["duplicateComplete"]
    assert "No active Matt Pocock workflow" in result["duplicateCancel"]
    assert result["entries"] == 3
    assert result["active"] == ["read", "matt_pocock_workflow"]


def test_command_alias_and_standalone_overlap_keep_gateway_state_separate() -> None:
    """Given an active workflow, model capabilities and human aliases do not mutate it."""
    result = run_typescript(HARNESS + """
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await command.handler("tight-red-loop investigate", r.ctx);
        const alias = r.deliveries().at(-1);
        await r.start(); const before = r.entries.length;
        const capability = await r.call("matt_pocock_workflow", { mode: "capability", capability: "research" });
        const after = r.entries.length;
        console.log(JSON.stringify({ alias, capability, before, after, active: r.active() }));
    """)
    assert result["alias"]["message"]["details"] == {
        "mode": "capability", "capability": "diagnosing-bugs", "request": "investigate",
    }
    assert result["before"] == result["after"] == 1
    assert result["capability"]["details"] == {"mode": "capability", "capability": "research"}
    assert "matt_pocock_active" in result["active"]


@pytest.mark.parametrize("command_text", ["complete unexpected", "status unexpected"])
def test_malformed_control_command_does_not_supersede_active_workflow(command_text: str) -> None:
    """Given an active workflow, an extra argument on a control command is rejected atomically."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await r.start();
        await command.handler({command_text!r}, r.ctx);
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({{ command: {command_text!r}, entries: r.entries.length, latest, deliveries: r.deliveries(), active: r.active(), notices: r.notices }}));
    """)
    assert result["command"] == command_text
    assert result["entries"] == 1, result
    assert result["latest"]["status"] == "active", result
    assert result["deliveries"] == [], result
    assert "matt_pocock_active" in result["active"], result
    assert result["notices"], result


@pytest.mark.parametrize("selection", ["Complete current workflow", "Transition current workflow"])
def test_active_menu_result_cannot_operate_on_a_replacement_workflow(selection: str) -> None:
    """An active menu opened for A cannot complete or transition replacement B."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await r.start();
        let openedResolve; const opened = new Promise(resolve => {{ openedResolve = resolve; }});
        let releaseMenu; let selects = 0;
        r.ctx.ui.select = async (_title, choices) => {{
          selects += 1;
          if (selects === 1) {{
            openedResolve();
            return new Promise(resolve => {{ releaseMenu = () => resolve({selection!r}); }});
          }}
          return "implement";
        }};
        const pendingMenu = command.handler("", r.ctx);
        await Promise.race([opened, new Promise(resolve => setTimeout(resolve, 100))]);
        await r.call("matt_pocock_active", {{ action: "cancel", reason: "replace A" }});
        await r.start();
        releaseMenu();
        await pendingMenu;
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({{ selection: {selection!r}, latest, entries: r.entries.length, selects, active: r.active() }}));
    """)
    assert result["latest"]["status"] == "active", result
    assert result["entries"] == 3, result
    assert result["selects"] == 1, result
    assert "matt_pocock_active" in result["active"]


def test_route_menu_result_cannot_overwrite_a_workflow_started_while_it_waited() -> None:
    """A delayed route choice from an inactive menu cannot replace a newer start."""
    result = run_typescript(HARNESS + """
        const r = runtime(); const command = r.commands.get("matt-pocock");
        let routeOpenedResolve; const routeOpened = new Promise(resolve => { routeOpenedResolve = resolve; });
        let releaseRoute; let selects = 0;
        r.ctx.ui.select = async (_title, choices) => {
          selects += 1;
          if (selects === 1) return "Start a workflow";
          routeOpenedResolve();
          return new Promise(resolve => { releaseRoute = () => resolve(choices[0]); });
        };
        const pendingMenu = command.handler("", r.ctx);
        await Promise.race([routeOpened, new Promise(resolve => setTimeout(resolve, 100))]);
        await r.start();
        releaseRoute();
        await pendingMenu;
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({ latest, entries: r.entries.length, selects, active: r.active() }));
    """)
    assert result["latest"]["status"] == "active", result
    assert result["entries"] == 1, result
    assert result["active"].count("matt_pocock_active") == 1


def test_menu_guard_survives_microtask_state_replacement_before_selection_returns() -> None:
    """A two-microtask replacement cannot slip between menu guard and dispatch."""
    result = run_typescript(HARNESS + """
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await r.start();
        const workItemA = r.entries.at(-1)?.data.workItemId;
        let replacePromise;
        r.ctx.ui.select = async () => {
          replacePromise = new Promise(resolve => {
            queueMicrotask(() => queueMicrotask(() => {
              void (async () => {
                if (r.entries.at(-1)?.data.status === "active") {
                  await r.call("matt_pocock_active", { action: "cancel", reason: "microtask replacement" });
                }
                await r.start();
                resolve();
              })();
            }));
          });
          await replacePromise;
          return "Complete current workflow";
        };
        await command.handler("", r.ctx);
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({ entries: r.entries.length, workItemA, latest, active: r.active() }));
    """)
    assert result["entries"] == 3, result
    assert result["latest"]["status"] == "active", result
    assert result["latest"]["workItemId"] != result["workItemA"], result
    assert "matt_pocock_active" in result["active"], result


@pytest.mark.parametrize("replacement", ["complete", "transition", "session_tree", "session_start"])
def test_inflight_selector_is_dismissed_when_workflow_state_is_replaced(replacement: str) -> None:
    """A late answer cannot leave a selector hanging after a state replacement."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); await r.start();
        let openedResolve; const opened = new Promise(resolve => {{ openedResolve = resolve; }});
        let selectorAborted = false;
        r.ctx.ui.select = (_title, _choices, {{ signal }}) => new Promise(resolve => {{
          openedResolve();
          signal.addEventListener("abort", () => {{ selectorAborted = true; resolve(undefined); }}, {{ once: true }});
        }});
        const pending = r.call("matt_pocock_ask", {{ question: "Scope?", options: ["A", "B"], recommended: "A" }});
        await Promise.race([opened, new Promise(resolve => setTimeout(resolve, 100))]);
        if ({replacement!r} === "complete") {{
          await r.call("matt_pocock_active", {{ action: "complete" }});
        }} else if ({replacement!r} === "transition") {{
          await r.call("matt_pocock_active", {{ action: "transition", target: "implement" }});
        }} else {{
          await r.events.get({replacement!r})({{}}, r.ctx);
        }}
        const outcome = await Promise.race([
          pending.then(value => ({{ kind: "settled", value }})),
          new Promise(resolve => setTimeout(() => resolve({{ kind: "timeout" }}), 150)),
        ]);
        console.log(JSON.stringify({{ replacement: {replacement!r}, selectorAborted, outcome }}));
    """)
    assert result["selectorAborted"] is True, result
    assert result["outcome"]["kind"] == "settled", result
    assert result["outcome"]["value"]["details"] == {"pending": True, "source": "aborted"}


@pytest.mark.parametrize("replacement", ["complete", "session_tree"])
def test_inflight_custom_input_is_dismissed_when_workflow_state_is_replaced(replacement: str) -> None:
    """A replacement aborts the custom-input phase itself and settles the ask."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); await r.start();
        let inputOpenedResolve; const inputOpened = new Promise(resolve => {{ inputOpenedResolve = resolve; }});
        let inputAborted = false;
        r.ctx.ui.select = async () => "Type custom answer...";
        r.ctx.ui.input = (_question, _placeholder, {{ signal }}) => new Promise(resolve => {{
          inputOpenedResolve();
          signal.addEventListener("abort", () => {{ inputAborted = true; resolve(undefined); }}, {{ once: true }});
        }});
        const pending = r.call("matt_pocock_ask", {{ question: "Scope?", options: ["A", "B"], recommended: "A" }});
        await Promise.race([inputOpened, new Promise(resolve => setTimeout(resolve, 100))]);
        if ({replacement!r} === "complete") {{
          await r.call("matt_pocock_active", {{ action: "complete" }});
        }} else {{
          await r.events.get("session_tree")({{}}, r.ctx);
        }}
        const outcome = await Promise.race([
          pending.then(value => ({{ kind: "settled", value }})),
          new Promise(resolve => setTimeout(() => resolve({{ kind: "timeout" }}), 150)),
        ]);
        console.log(JSON.stringify({{ replacement: {replacement!r}, inputAborted, outcome }}));
    """)
    assert result["inputAborted"] is True, result
    assert result["outcome"]["kind"] == "settled", result
    assert result["outcome"]["value"]["details"] == {"pending": True, "source": "aborted"}, result


# ── test_adversarial_resources.py ──

from matt_pocock_helpers import run_typescript


def test_delivery_ids_are_canonicalized_and_unknown_history_is_dropped() -> None:
    result = run_typescript(
        """
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        const delta = resolveProcedureDelta("diagnosing-bugs", [], [
          " tight-red-loop ", "diagnosing-bugs", "tight-red-loop", "unknown-old-id",
        ]);
        console.log(JSON.stringify(delta));
        """
    )
    assert result["content"] == ""
    assert result["delivered"] == ["diagnosing-bugs"]


def test_legacy_state_without_delivery_tracking_can_transition_and_deliver() -> None:
    result = run_typescript(
        """
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";
        const legacy = {
          version: 1, workItemId: "legacy", route: "hard-bug",
          procedure: "diagnosing-bugs", phase: "feedback-loop",
          status: "active", loadedReferences: [],
        };
        const next = transitionState(legacy, "implement");
        const delta = resolveProcedureDelta(next.procedure, next.loadedReferences, next.deliveredProcedures);
        console.log(JSON.stringify({ next, delta }));
        """
    )
    assert result["next"]["deliveredProcedures"] == []
    assert "implement" in result["delta"]["delivered"]


def test_link_rewriting_covers_resource_paths_only() -> None:
    """A resource link becomes a procedure link; a URL, a title and an unknown target survive.

    The rewriter must not touch an external URL even when its tail names a resource,
    because only catalogue resources are what the model can load.
    """
    result = run_typescript(
        """
        import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { fileURLToPath, pathToFileURL } from "node:url";
        const sourcePackage = fileURLToPath(new URL("./packages/matt-pocock/", import.meta.url));
        const isolatedPackage = mkdtempSync(join(tmpdir(), "matt-link-rewrite-"));
        cpSync(join(sourcePackage, "src"), join(isolatedPackage, "src"), { recursive: true });
        for (const kind of ["procedures", "references", "assets"]) {
          cpSync(join(sourcePackage, kind), join(isolatedPackage, kind), { recursive: true });
        }
        const { resolveProcedureBundle } = await import(
          pathToFileURL(join(isolatedPackage, "src/resolver.ts")).href
        );
        try {
          writeFileSync(join(isolatedPackage, "procedures/pr.md"), [
            "# Link forms",
            "",
            "- external resource tail: [threat model](https://evil.example/DEEPENING.md)",
            "- protocol-relative tail: [pr](//host.example/DEEPENING.md)",
            "- bare host path: [doc](www.example.com/DEEPENING.md)",
            '- titled cross-directory link: [glossary](../references/bdd.md "the title")',
            "- anchored sibling link: [tests](tests.md#loop)",
            "- unknown target: [missing](nope.md)",
          ].join("\\n"));
          console.log(JSON.stringify({ content: resolveProcedureBundle("pr").content }));
        } finally {
          rmSync(isolatedPackage, { recursive: true, force: true });
        }
        """
    )
    content = str(result["content"])
    assert "](https://evil.example/DEEPENING.md)" in content
    assert "](procedure:DEEPENING)" not in content
    assert "](//host.example/DEEPENING.md)" in content
    assert "](www.example.com/DEEPENING.md)" in content
    assert '](procedure:bdd "the title")' in content
    assert "](../references/bdd.md \"the title\")" not in content
    assert "](procedure:tests#loop)" in content
    assert "](nope.md)" in content
    assert "](procedure:" in content


def test_multibyte_bundle_limit_counts_utf8_bytes_and_rejects_overflow() -> None:
    result = run_typescript(
        """
        import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { fileURLToPath, pathToFileURL } from "node:url";
        const sourcePackage = fileURLToPath(new URL("./packages/matt-pocock/", import.meta.url));
        const isolatedPackage = mkdtempSync(join(tmpdir(), "matt-boundary-package-"));
        cpSync(join(sourcePackage, "src"), join(isolatedPackage, "src"), { recursive: true });
        for (const kind of ["procedures", "references", "assets"]) {
          cpSync(join(sourcePackage, kind), join(isolatedPackage, kind), { recursive: true });
        }
        const { MAX_PROCEDURE_BUNDLE_BYTES, resolveProcedureBundle } = await import(
          pathToFileURL(join(isolatedPackage, "src/resolver.ts")).href
        );
        const prefix = `<procedure-source id="pr" source="procedure/pr">\\n`;
        const suffix = `\\n</procedure-source>`;
        const unit = "界";
        const bodyBytes = MAX_PROCEDURE_BUNDLE_BYTES - Buffer.byteLength(prefix + suffix, "utf8");
        const bodyForBytes = (bytes) => unit.repeat(Math.floor(bytes / Buffer.byteLength(unit, "utf8")))
          + "a".repeat(bytes % Buffer.byteLength(unit, "utf8"));
        const exactBody = bodyForBytes(bodyBytes);
        const overflowBody = bodyForBytes(bodyBytes + 1);
        let exact = 0;
        let overflow = "";
        try {
          writeFileSync(join(isolatedPackage, "procedures/pr.md"), exactBody);
          exact = resolveProcedureBundle("pr").byteLength;
          writeFileSync(join(isolatedPackage, "procedures/pr.md"), overflowBody);
          try { resolveProcedureBundle("pr"); } catch (error) { overflow = String(error); }
          console.log(JSON.stringify({ exact, exactChars: exactBody.length, max: MAX_PROCEDURE_BUNDLE_BYTES, overflow }));
        } finally {
          rmSync(isolatedPackage, { recursive: true, force: true });
        }
        """
    )
    assert result["exact"] == result["max"]
    assert result["exactChars"] < result["max"]
    assert "maximum" in result["overflow"]


def test_catalog_manifest_derives_all_resource_edges_and_transition_guards() -> None:
    result = run_typescript(
        """
        import {
          findProcedure, normalizeProcedureId, procedureCatalog,
        } from "./packages/matt-pocock/src/catalog.ts";
        import {
          MAX_PROCEDURE_BUNDLE_BYTES, resolveAccessibleReference, resolveProcedureBundle,
        } from "./packages/matt-pocock/src/resolver.ts";
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";

        const errors = [];
        const closure = (id, seen = new Set()) => {
          const definition = findProcedure(id);
          if (!definition) { errors.push(`missing dependency: ${id}`); return []; }
          if (seen.has(definition.id)) return [];
          seen.add(definition.id);
          return [definition.id, ...(definition.requires ?? []).flatMap((dependency) => closure(dependency, seen))];
        };
        let aliasCount = 0;
        let disclosureCount = 0;
        let legalTransitionCount = 0;
        let illegalTransitionCount = 0;
        for (const definition of procedureCatalog) {
          const bundle = resolveProcedureBundle(definition.id);
          const expected = closure(definition.id);
          if (bundle.loaded.join("|") !== expected.join("|")) errors.push(`${definition.id}: closure order`);
          if (bundle.loaded.length !== new Set(bundle.loaded).size) errors.push(`${definition.id}: duplicate closure`);
          if (!bundle.loaded.includes(definition.id) || bundle.byteLength > MAX_PROCEDURE_BUNDLE_BYTES) {
            errors.push(`${definition.id}: invalid bundle boundary`);
          }
          for (const alias of definition.aliases ?? []) {
            aliasCount++;
            if (findProcedure(alias)?.id !== definition.id || normalizeProcedureId(`  ${alias}.md `) !== definition.id) {
              errors.push(`${definition.id}: alias ${alias}`);
            }
          }
          for (const reference of definition.discloses ?? []) {
            disclosureCount++;
            try {
              const resolved = resolveAccessibleReference(definition.id, [], reference);
              if (resolved.root !== findProcedure(reference)?.id) errors.push(`${definition.id}: disclosure ${reference}`);
            } catch (error) {
              errors.push(`${definition.id}: disclosure ${reference}: ${String(error)}`);
            }
          }
          for (const placement of definition.workflows ?? []) {
            const state = {
              version: 1, workItemId: `batch-${definition.id}`, route: placement.route,
              procedure: definition.id, phase: placement.phase, status: "active",
              loadedReferences: [], deliveredProcedures: [],
            };
            for (const target of placement.allowedNext) {
              try {
                const next = transitionState(state, target);
                legalTransitionCount++;
                if (next.procedure !== findProcedure(target)?.id) errors.push(`${definition.id}: target ${target}`);
              } catch (error) { errors.push(`${definition.id}: legal ${target}: ${String(error)}`); }
            }
            const before = JSON.stringify(state);
            let rejected = false;
            try { transitionState(state, "__adversarial-invalid-target__"); }
            catch { rejected = true; }
            illegalTransitionCount++;
            if (!rejected) errors.push(`${definition.id}: invalid transition accepted`);
            if (JSON.stringify(state) !== before) errors.push(`${definition.id}: invalid transition mutated state`);
          }
        }
        console.log(JSON.stringify({
          catalog: procedureCatalog.length, aliasCount, disclosureCount,
          legalTransitionCount, illegalTransitionCount, errors,
        }));
        """
    )
    assert result["errors"] == []
    assert result["catalog"] >= 1
    assert result["aliasCount"] >= 1
    assert result["disclosureCount"] >= 1
    assert result["legalTransitionCount"] >= 1
    assert result["illegalTransitionCount"] >= 1


def test_latest_malformed_record_does_not_resurrect_older_active_workflow() -> None:
    result = run_typescript(
        """
        import { latestWorkflowRecord } from "./packages/matt-pocock/src/workflow.ts";
        const active = {
          version: 1, workItemId: "w", route: "hard-bug", procedure: "diagnosing-bugs",
          phase: "feedback-loop", status: "active", loadedReferences: [],
        };
        const malformed = { version: 2, workItemId: "w", route: "hard-bug", procedure: "diagnosing-bugs" };
        console.log(JSON.stringify({ record: latestWorkflowRecord([
          { type: "custom", customType: "matt-pocock-workflow", data: active },
          { type: "custom", customType: "matt-pocock-workflow", data: malformed },
        ]) ?? null }));
        """
    )
    assert result["record"] is None


def test_transition_rejects_a_route_procedure_with_a_corrupted_phase() -> None:
    result = run_typescript(
        """
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";
        const state = {
          version: 1, workItemId: "corrupt", route: "hard-bug",
          procedure: "diagnosing-bugs", phase: "not-the-feedback-loop",
          status: "active", loadedReferences: [], deliveredProcedures: [],
        };
        let error = "";
        try { transitionState(state, "implement"); } catch (caught) { error = String(caught); }
        console.log(JSON.stringify({ error }));
        """
    )
    assert "invalid current procedure state" in result["error"]
