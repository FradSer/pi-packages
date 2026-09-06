import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        input=script,
    )


def test_live_capability_bundle_and_disclosures() -> None:
    result = run_node('''
import assert from "node:assert/strict";
import { resolver } from "./packages/impeccable/src/resolver.ts";
const bundle = resolver.load("live", "user");
assert.equal(bundle.root, "live");
for (const id of ["live", "setup", "principles"]) {
  assert.equal(bundle.content.split(`<impeccable-source id="${id}">`).length, 2);
}
assert.ok(bundle.byteLength <= 65536, `live bundle too large: ${bundle.byteLength}`);
const disclosed = bundle.availableReferences.map(edge => edge.id);
assert.ok(disclosed.includes("live-setup"));
assert.ok(disclosed.includes("components"));
assert.ok(!bundle.content.includes("{{PKG_DIR}}"));
assert.ok(!/\\.agents\\/skills|\\.pi\\/agent\\/skills|SKILL\\.md/.test(bundle.content));
assert.ok(bundle.content.includes("live.mjs"));
const setup = resolver.load("live", "model", "live-setup");
assert.equal(setup.root, "live-setup");
assert.ok(setup.byteLength <= 65536);
console.log(JSON.stringify({ bytes: bundle.byteLength, disclosed }));
''')
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["bytes"] > 0
    assert "live-setup" in payload["disclosed"]


def test_live_helper_scripts_ship_and_parse() -> None:
    scripts = sorted([
        *PACKAGE.glob("scripts/live*.mjs"),
        *PACKAGE.glob("scripts/live*.js"),
        *PACKAGE.glob("scripts/live/*.mjs"),
        *PACKAGE.glob("scripts/live/frameworks/*.mjs"),
        PACKAGE / "scripts/detect-csp.mjs",
        *(PACKAGE / "scripts/lib").glob("*.mjs"),
    ])
    assert len(scripts) >= 60, f"unexpectedly few live runtime files: {len(scripts)}"
    for script in scripts:
        check = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
        assert check.returncode == 0, f"{script.name}: {check.stderr}"


def test_live_boot_reports_actionable_context_in_empty_project(tmp_path: Path) -> None:
    check = subprocess.run(
        ["node", str(PACKAGE / "scripts/live.mjs")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert check.returncode == 0, check.stderr
    payload = json.loads(check.stdout)
    assert payload["ok"] is False
    assert payload["error"] == "context_missing"
    assert set(payload["missing"]) == {"PRODUCT.md", "DESIGN.md"}
    assert "nextCommand" not in payload
    assert "PRODUCT.md" in payload["nextStep"]
    assert "impeccable init" not in check.stdout


def test_copy_edit_agent_selects_pi_first() -> None:
    result = run_node('''
import assert from "node:assert/strict";
import { chooseCopyEditAgent, describeNoProviderError } from "./packages/impeccable/scripts/live-copy-edit-agent.mjs";
const exists = command => ["pi", "codex", "claude"].includes(command);
assert.equal(chooseCopyEditAgent({ exists, authCheck: () => true }), "pi");
assert.equal(chooseCopyEditAgent({ exists, authCheck: command => command !== "pi" }), "codex");
assert.equal(chooseCopyEditAgent({ exists, authCheck: () => false, chatAvailable: () => true }), "chat");
assert.equal(chooseCopyEditAgent({ exists, authCheck: () => true, env: { IMPECCABLE_LIVE_COPY_AGENT: "pi" } }), "pi");
assert.equal(chooseCopyEditAgent({ exists, authCheck: () => true, env: { IMPECCABLE_LIVE_COPY_AGENT: "codex" } }), "codex");
assert.equal(chooseCopyEditAgent({ exists, authCheck: () => true, env: { IMPECCABLE_LIVE_COPY_AGENT: "off" } }), null);
assert.equal(chooseCopyEditAgent({ exists: () => false, authCheck: () => false }), null);
assert.match(describeNoProviderError({ exists, chatAvailable: () => false }), /Pi CLI/);
console.log("ok");
''')
    assert result.returncode == 0, result.stdout + result.stderr


def test_live_vocabulary_offers_only_shipped_actions() -> None:
    result = run_node('''
import assert from "node:assert/strict";
import { VISUAL_ACTIONS } from "./packages/impeccable/scripts/live/vocabulary.mjs";
assert.deepEqual(VISUAL_ACTIONS, ["impeccable", "polish", "typeset", "colorize", "layout", "animate"]);
console.log("ok");
''')
    assert result.returncode == 0, result.stdout + result.stderr


def test_live_provenance_covers_runtime_and_documents() -> None:
    provenance = json.loads((PACKAGE / "runtime-provenance.json").read_text())
    destinations = {record["destination"] for record in provenance["files"]}
    for relative in [
        "scripts/live.mjs",
        "scripts/live-poll.mjs",
        "scripts/live-server.mjs",
        "scripts/live-browser.js",
        "scripts/live-copy-edit-agent.mjs",
        "scripts/detect-csp.mjs",
        "scripts/live/vocabulary.mjs",
        "scripts/live/project-ignores.mjs",
        "scripts/live/instructions.mjs",
        "scripts/live/frameworks/sveltekit.mjs",
        "scripts/lib/impeccable-paths.mjs",
        "scripts/lib/staleness.mjs",
        "procedures/live.md",
        "procedures/live-setup.md",
    ]:
        assert relative in destinations, relative
    by_destination = {record["destination"]: record for record in provenance["files"]}
    assert by_destination["scripts/live-browser.js"]["disposition"] == "adapted"
    assert by_destination["scripts/live/roots.mjs"]["disposition"] == "retained"
