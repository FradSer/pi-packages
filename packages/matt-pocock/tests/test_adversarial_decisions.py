"""Adversarial boundaries for the Pi v1 decision and native dialog adapters."""
from __future__ import annotations

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
        import {{ macosChooseFromList, macosPrompt, isNativeDialogSupported, loadConfig }} from "./packages/matt-pocock/src/native-dialog.ts";
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
          try { await macosPrompt({ message: "q" }, env); }
          catch (value) { errors[mode] = String(value); }
        }
        console.log(JSON.stringify({ errors }));
        ''',
    )
    assert set(result["errors"]) == {"malformed", "null", "other-button", "missing-button", "bad-text"}
    assert all("Invalid native prompt result" in error for error in result["errors"].values())


def test_native_timeout_rejects_node_timer_overflow_and_list_is_single_select(tmp_path: Path) -> None:
    result = native_harness(
        tmp_path,
        '''
        process.env.MP_NATIVE_MODE = "delayed";
        let hugeError = "";
        try { await macosPrompt({ message: "q", timeoutSeconds: 2147484 }, env); }
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
          { message: "q", buttons: ["A", "A"] },
          { message: "q", buttons: ["A", "B"], defaultButton: "C" },
          { message: "q", buttons: ["A", "B"], cancelButton: "C" },
          { message: "q", timeoutSeconds: Infinity },
        ]) {
          try { await macosPrompt(options, env); }
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
        const cancelled = await macosPrompt({ message: "q" }, env);
        process.env.MP_NATIVE_MODE = "failure";
        let error = "";
        try { await macosPrompt({ message: "q" }, env); }
        catch (value) { error = String(value); }
        console.log(JSON.stringify({ cancelled, error }));
        ''',
    )
    assert result["cancelled"] == {"action": "cancelled", "gaveUp": False}
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
