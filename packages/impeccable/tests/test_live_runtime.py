"""Impeccable live capability, copy-edit agent, and HTTP body limit contracts."""
from __future__ import annotations

import http.client
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
MAX_BODY_BYTES = 1024 * 1024


def run_node(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for runtime tests"
    return subprocess.run(
        [node, "--import", "tsx/esm", "--input-type=module"],
        cwd=ROOT,
        env=env,
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


def test_copy_edit_agent_selects_pi_first(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in ("pi", "codex", "claude"):
        executable = bin_dir / command
        executable.write_text('#!/bin/sh\n[ "$#" -eq 1 ] && [ "$1" = "--version" ]\n')
        executable.chmod(0o755)
    result = run_node('''
import assert from "node:assert/strict";
import { unlinkSync } from "node:fs";
import path from "node:path";
import { chooseCopyEditAgent, describeNoProviderError } from "./packages/impeccable/scripts/live-copy-edit-agent.mjs";
const auto = { env: {} };
assert.equal(chooseCopyEditAgent({ ...auto, authCheck: () => true }), "pi");
assert.equal(chooseCopyEditAgent({ ...auto, authCheck: command => command !== "pi" }), "codex");
assert.equal(chooseCopyEditAgent({ ...auto, authCheck: command => command === "claude" }), "claude");
assert.equal(chooseCopyEditAgent({ ...auto, authCheck: () => false, chatAvailable: () => true }), "chat");
assert.equal(chooseCopyEditAgent({ ...auto, authCheck: () => false }), null);
const noAuthProbe = () => { throw new Error("Explicit selection must not authenticate a CLI"); };
for (const provider of ["pi", "codex", "claude"]) {
  assert.equal(chooseCopyEditAgent({ authCheck: noAuthProbe, env: { IMPECCABLE_LIVE_COPY_AGENT: provider } }), provider);
  unlinkSync(path.join(process.env.PATH, provider));
  assert.equal(chooseCopyEditAgent({ authCheck: noAuthProbe, env: { IMPECCABLE_LIVE_COPY_AGENT: provider } }), null);
}
for (const mode of ["off", "unsupported"]) {
  assert.equal(chooseCopyEditAgent({ authCheck: noAuthProbe, env: { IMPECCABLE_LIVE_COPY_AGENT: mode } }), null);
}
assert.equal(chooseCopyEditAgent({ authCheck: noAuthProbe, env: { IMPECCABLE_LIVE_COPY_AGENT: "mock" } }), "mock");
assert.equal(chooseCopyEditAgent({ env: {} }), null);
assert.match(describeNoProviderError({ env: {} }), /Pi CLI: not installed/);
console.log("ok");
''', env={"PATH": str(bin_dir), "HOME": str(tmp_path), "IMPECCABLE_LIVE_COPY_AGENT": "off"})
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


def test_bounded_body_reader_preserves_utf8_and_discards_aborted_requests() -> None:
    result = subprocess.run(
        ["node", str(PACKAGE / "tests/http_body_harness.mjs")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def live_server(tmp_path: Path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        ["node", str(PACKAGE / "scripts/live-server.mjs"), f"--port={port}"],
        cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            assert process.poll() is None, process.stderr.read().decode()
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("Live server did not start")
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()


@pytest.mark.parametrize("route", ["/events", "/poll", "/manual-edit-stash", "/manual-edit-repair-decision"])
@pytest.mark.parametrize("chunked", [False, True])
def test_live_json_bodies_are_rejected_before_unbounded_aggregation(live_server: int, route: str, chunked: bool) -> None:
    body = b'{"padding":"' + b"x" * MAX_BODY_BYTES + b'"}'
    connection = http.client.HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        connection.request(
            "POST", route,
            body=iter([body[:30], body[30:]]) if chunked else body,
            headers={"Content-Type": "application/json"}, encode_chunked=chunked,
        )
        response = connection.getresponse()
        assert response.status == 413, response.read().decode()
        assert b"large" in response.read().lower()
    finally:
        connection.close()
    connection = http.client.HTTPConnection("127.0.0.1", live_server, timeout=5)
    try:
        connection.request("POST", route, body=b"{}")
        response = connection.getresponse()
        assert response.status == 401
        response.read()
    finally:
        connection.close()
