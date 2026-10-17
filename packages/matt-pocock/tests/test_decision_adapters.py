"""Both UI adapters execute the same decision contract through the registered tool."""
from __future__ import annotations

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
