"""Impeccable bundle, taste provenance, and detector/context runtime contracts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]


def run_tsx(script: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        input=script,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def run_script(name: str, cwd: Path, *args: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if home:
        env["HOME"] = str(home)
    return subprocess.run(
        ["node", str(PACKAGE / "scripts" / name), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )


# ── Package & topic bundle contracts ─────────────────────────────────

def test_production_command_and_model_bundles() -> None:
    result = run_tsx('''
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolver } from "./packages/impeccable/src/resolver.ts";
import register from "./packages/impeccable/src/index.ts";
const packageRoot = fileURLToPath(new URL("./packages/impeccable/", import.meta.url));
const commands = new Map(), tools = [], sent = [];
register({
  registerCommand: (id, command) => commands.set(id, command),
  registerTool: tool => tools.push(tool),
  sendUserMessage: (...args) => sent.push(args),
  sendMessage: (message, options) => { sent.push([message.content, options, message]); },
});
const output = {};
for (const capability of ["polish", "animate"]) {
  const bundle = resolver.load(capability, "model");
  const expected = capability === "polish"
    ? ["polish", "setup", "principles", "components", "accessibility", "motion"]
    : ["animate", "setup", "principles", "motion", "accessibility"];
  assert.deepEqual(bundle.loaded, expected);
  for (const id of expected) {
    assert.equal(bundle.content.split(`<impeccable-source id="${id}">`).length, 2);
  }
  assert.ok(bundle.content.includes(packageRoot + "scripts/context.mjs"));
  assert.ok(bundle.content.includes(packageRoot + "scripts/detect.mjs"));
  for (const script of ["context.mjs", "detect.mjs"]) {
    assert.ok(existsSync(packageRoot + "scripts/" + script), `Missing packaged script: ${script}`);
  }
  assert.ok(!/\\{\\{PKG_DIR\\}\\}|SKILL\\.md|\\.agents\\/skills|\\.pi\\/agent\\/skills/.test(bundle.content));
  assert.ok(bundle.byteLength <= 65536);
  const request = 'src/My Page.tsx  preserve this spacing';
  await commands.get("impeccable").handler(capability + " " + request, { hasUI: false });
  const model = await tools[0].execute("bundle", { capability });
  assert.equal(model.content[0].text, bundle.content);
  const text = sent.at(-1)[0];
  assert.ok(text.startsWith(`Plan for "${request}" (in order):`));
  assert.ok(text.includes(`1. /impeccable ${capability} — `));
  assert.ok(text.endsWith(bundle.content + "\\n\\nUser target/request:\\n" + request));
  assert.deepEqual(sent.at(-1)[1], { deliverAs: "followUp", triggerTurn: true });
  assert.equal(sent.at(-1)[2].customType, "impeccable-procedure");
  assert.equal(sent.at(-1)[2].display, true);
  assert.equal(sent.at(-1)[2].details.request, request);
  assert.deepEqual(sent.at(-1)[2].details.loaded.map(entry => entry.id), [capability]);
  assert.ok(sent.at(-1)[2].details.routing[0].startsWith("Plan for "));
  assert.ok(sent.at(-1)[2].details.routing[1].includes(`/impeccable ${capability} — `));
  output[capability] = { loaded: bundle.loaded, bytes: bundle.byteLength };
}
assert.equal(sent.length, 2);
console.log(JSON.stringify(output));
''')
    bundles = json.loads(result.stdout)
    assert set(bundles) == {"polish", "animate"}


def test_all_canonical_reference_links_are_reachable() -> None:
    run_tsx('''
import assert from "node:assert/strict";
import { resolver } from "./packages/impeccable/src/resolver.ts";
const failures = [];
for (const capability of resolver.capabilities) {
  const actor = capability.invocation === "user" ? "user" : "model";
  const queue = [resolver.load(capability.id, actor)];
  const visited = new Set();
  while (queue.length) {
    const bundle = queue.shift();
    for (const match of bundle.content.matchAll(/\\]\\(impeccable:([^\\s)]+)\\)/g)) {
      const linkTarget = match[1];
      if (visited.has(`${capability.id}->${linkTarget}`)) continue;
      visited.add(`${capability.id}->${linkTarget}`);
      try {
        queue.push(resolver.load(capability.id, actor, linkTarget));
        resolver.load(capability.id, actor, "impeccable:" + linkTarget);
      } catch (error) {
        failures.push(`${capability.id} via ${bundle.root} -> ${linkTarget}: ${error.message}`);
      }
    }
  }
}
assert.deepEqual(failures, []);
''')


def test_focused_refinement_topic_bundles() -> None:
    run_tsx('''
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { resolver } from "./packages/impeccable/src/resolver.ts";
const root = fileURLToPath(new URL("./packages/impeccable/", import.meta.url));
const topics = { typeset: "typography", colorize: "color", layout: "taste-layout", clarify: "writing" };
for (const [capability, topic] of Object.entries(topics)) {
  const bundle = resolver.load(capability, "model");
  assert.deepEqual(bundle.loaded, [capability, "setup", "principles", topic, "accessibility"]);
  assert.ok(bundle.content.includes(root + "scripts/context.mjs"));
  assert.ok(!bundle.content.includes("{{PKG_DIR}}"));
  assert.ok(bundle.byteLength <= 65536);
  assert.ok(!bundle.loaded.some(id => /jakub|emil|better-/.test(id)));
  for (const other of Object.values(topics).filter(id => id !== topic)) {
    assert.ok(!bundle.loaded.includes(other));
  }
  const reference = resolver.load("polish", "model", topic);
  assert.deepEqual(reference.loaded, [topic, "accessibility"]);
  assert.ok(!reference.content.includes("{{PKG_DIR}}"));
  assert.ok(reference.byteLength <= 65536);
  assert.ok(bundle.availableReferences.length > 0);
  for (const edge of bundle.availableReferences) {
    assert.ok(edge.when.length > 0);
    assert.ok(resolver.load(capability, "model", edge.id).loaded.includes(edge.id));
  }
}
const polish = resolver.load("polish", "model");
for (const id of Object.values(topics)) {
  assert.ok(polish.availableReferences.some(edge => edge.id === id));
  assert.ok(!polish.loaded.includes(id));
}
assert.ok(resolver.load("animate", "model").availableReferences.some(edge => edge.id === "components"));
''')


# ── Taste library & provenance contracts ─────────────────────────────

def test_canonical_press_feedback_contract() -> None:
    components = (PACKAGE / "references/taste/components.md").read_text()
    assert "0.96" in components
    assert "150ms" in components or "150 ms" in components
    assert "keyboard" in components.lower()
    assert "token" in components.lower()


def test_canonical_motion_and_accessibility_contract() -> None:
    motion = (PACKAGE / "references/taste/motion.md").read_text()
    accessibility = (PACKAGE / "references/taste/accessibility.md").read_text()
    assert "interrupt" in motion.lower()
    assert "gesture" in motion.lower()
    assert "transition" in motion.lower()
    assert "reduced-motion" in accessibility.lower()
    assert "static" in accessibility.lower() or "nonspatial" in accessibility.lower()


def test_taste_provenance_maps_real_anchors_and_pending_scope() -> None:
    provenance = json.loads((PACKAGE / "taste-provenance.json").read_text())
    assert provenance["coverage"] == "first-slice"
    assert len(provenance["inventory"]) == 65
    assert any(item["disposition"] == "pending" for item in provenance["inventory"])
    assert any(item["disposition"] == "excluded" for item in provenance["inventory"])
    assert provenance["conflicts"]["press-feedback"]["selected"] == "0.96 / 150ms"
    for mapping in provenance["mappings"]:
        assert re.fullmatch(r"[a-f0-9]{64}", mapping["sha256"])
        assert mapping["sourceSection"]
        assert mapping["rationale"]
        for destination in mapping["destinations"]:
            path, anchor = destination.split("#", 1)
            content = (PACKAGE / path).read_text()
            headings = re.findall(r"^## (.+)$", content, re.MULTILINE)
            anchors = [re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings]
            assert anchor in anchors


def test_taste_scope_and_nonspatial_feedback() -> None:
    root = PACKAGE / "references/taste"
    motion = (root / "motion.md").read_text()
    assert "presentation value" in motion
    assert "release velocity" in motion
    assert "not inherently impossible to interrupt" in motion
    accessibility = (root / "accessibility.md").read_text()
    assert "prefers-reduced-motion: no-preference" in accessibility
    assert "5 seconds" in accessibility
    assert "Aria-disabled" in accessibility
    for path in root.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            assert (path.parent / target.split("#", 1)[0]).is_file()


def test_source_mapping_selectors_match_inventory_fingerprints() -> None:
    provenance = json.loads((PACKAGE / "taste-provenance.json").read_text())
    inventory = {
        (item["source"], item["sourcePath"]): item
        for item in provenance["inventory"]
    }
    assert len(inventory) == 65
    assert sum(key[0] == "jakubkrehel" for key in inventory) == 46
    assert sum(key[0] == "emilkowalski" for key in inventory) == 19
    for mapping in provenance["mappings"]:
        item = inventory[(mapping["source"], mapping["sourcePath"])]
        assert item["sha256"] == mapping["sha256"]
        assert mapping["sourceSection"] in item["mappedSectionSelectors"]
    assert any(len(mapping["destinations"]) > 1 for mapping in provenance["mappings"])
    press_sources = {
        mapping["source"]
        for mapping in provenance["mappings"]
        if "references/taste/components.md#press-feedback" in mapping["destinations"]
    }
    assert press_sources == {"jakubkrehel", "emilkowalski"}
    assert all(item["reason"] for item in inventory.values())


def test_focused_topics_preserve_concrete_decisions() -> None:
    expected = {
        "layout": ["2×", "12px", "24px", "16–32px", "container", "pseudo-localization"],
        "typography": ["60–75", "1.4", "16px", "font-synthesis", "font-optical-sizing", "<bdi>"],
        "color": ["APCA", "4.5:1", "24px", "15°", "culori", "Radix", "contract"],
        "writing": ["ON state", "plural", "consequence", "placeholder", "recovery"],
    }
    for topic, values in expected.items():
        content = (PACKAGE / f"references/taste/{topic}.md").read_text()
        for value in values:
            assert value in content
        assert "accessibility.md#" in content
        for target in re.findall(r"\]\(([^)]+)\)", content):
            assert (PACKAGE / "references/taste" / target.split("#", 1)[0]).is_file()


def test_expansion_has_source_section_provenance() -> None:
    provenance = json.loads((PACKAGE / "taste-provenance.json").read_text())
    for topic in ("layout", "typography", "color", "writing"):
        prefix = f"references/taste/{topic}.md#"
        mappings = [m for m in provenance["mappings"] if any(d.startswith(prefix) for d in m["destinations"])]
        assert mappings, topic
        assert all(m["sourceSection"] and m["sha256"] and m["rationale"] for m in mappings)
    assert len(provenance["inventory"]) == 65
    assert len(provenance["mappings"]) > 93


# ── Context & static detector runtime contracts ──────────────────────

def test_context_target_and_isolation(tmp_path: Path) -> None:
    project = tmp_path / "target with spaces"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    empty = run_script("context.mjs", project, home=home)
    assert empty.returncode == 0, empty.stderr
    assert "NO_PRODUCT_MD" in empty.stdout
    assert not list(home.iterdir())
    for forbidden in ["UPDATE_AVAILABLE", "SUBAGENT", "build-phase", "reference/init.md", "npx"]:
        assert forbidden not in empty.stdout
    (project / "PRODUCT.md").write_text("# Product\nUnique fixture product")
    (project / "DESIGN.md").write_text("# Design\nUnique fixture design")
    result = run_script("context.mjs", project, home=home)
    assert result.returncode == 0, result.stderr
    assert "Unique fixture product" in result.stdout
    assert "Unique fixture design" in result.stdout
    assert str(project.resolve()) in result.stdout
    assert not list(home.iterdir())


def test_context_monorepo(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["apps/*"]}))
    for app in ["alpha", "beta"]:
        target = tmp_path / "apps" / app
        target.mkdir(parents=True)
        (target / "PRODUCT.md").write_text(f"# {app} product")
    result = run_script("context.mjs", tmp_path, "--target", "apps/beta")
    assert result.returncode == 0, result.stderr
    assert "# beta product" in result.stdout
    assert "# alpha product" not in result.stdout
    missing = run_script("context.mjs", tmp_path, "--target", "apps/missing")
    assert missing.returncode != 0
    assert "TARGET" in missing.stdout + missing.stderr
    selection = run_script("context.mjs", tmp_path)
    assert "TARGET_SELECTION_REQUIRED" in selection.stdout


def test_static_detector_real_findings(tmp_path: Path) -> None:
    bad = tmp_path / "bad fixture.html"
    bad.write_text('<!doctype html><html><body><h1>Account</h1><h3>Settings</h3></body></html>')
    result = run_script("detect.mjs", tmp_path, "--json", str(bad))
    assert result.returncode == 2, result.stderr + result.stdout
    findings = json.loads(result.stdout)
    assert any(f["antipattern"] == "skipped-heading" for f in findings)
    clean = tmp_path / "clean.html"
    clean.write_text('<p>Account settings</p>')
    result = run_script("detect.mjs", tmp_path, "--json", str(clean))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_static_detector_rejects_external_capabilities(tmp_path: Path) -> None:
    for args in [("--json",), ("--json", "https://example.com")]:
        result = run_script("detect.mjs", tmp_path, *args)
        assert result.returncode == 1
        assert "explicit local" in result.stderr


def test_native_and_advisory_limits(tmp_path: Path) -> None:
    (tmp_path / "PRODUCT.md").write_text("# Product\n## Platform\nios\n")
    result = run_script("context.mjs", tmp_path)
    assert "NATIVE_SUPPLEMENT_UNAVAILABLE" in result.stdout
    style = tmp_path / "style.css"
    style.write_text("p { font-family: Inter; }")
    result = run_script("detect.mjs", tmp_path, "--json", str(style))
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert any(f["antipattern"] == "overused-font" and f["advisory"] for f in findings)


def test_runtime_provenance() -> None:
    provenance = json.loads((PACKAGE / "runtime-provenance.json").read_text())
    assert provenance["revision"] == "63b04e2530f5c7b41ea83c133daab24f34912456"
    destinations = {record["destination"] for record in provenance["files"]}
    assert all(str(p.relative_to(PACKAGE)) in destinations for p in (PACKAGE / "scripts").rglob("*.mjs")
               if p.name != "check-upstream-sync.mjs")
    for record in provenance["files"]:
        data = (PACKAGE / record["destination"]).read_bytes()
        if record["disposition"] == "retained":
            assert hashlib.sha256(data).hexdigest() == record["sha256"]
        elif record["destination"].endswith(".mjs"):
            assert b"Modified for @fradser/pi-impeccable" in data
    assert "Copyright 2025 Paul Bakaus" in (PACKAGE / "licenses/impeccable-Apache-2.0.txt").read_text()
    assert provenance["licenses"]["jakub"]["revision"] == "267330e1adfc66a718fb65fa6918c1f06d0a689e"


def test_low_contrast_source_evidence(tmp_path: Path) -> None:
    target = tmp_path / "contrast.html"
    target.write_text('<!doctype html><html><body><p style="color:#aaaaaa;background-color:#ffffff;font-size:16px">Account settings details</p></body></html>')
    result = run_script("detect.mjs", tmp_path, "--json", str(target))
    assert result.returncode == 2, result.stderr + result.stdout
    findings = json.loads(result.stdout)
    contrast = next(f for f in findings if f["antipattern"] == "low-contrast")
    assert contrast["file"] == str(target)
    assert contrast["snippet"]
    assert "Static estimates" in json.loads((PACKAGE / "runtime-provenance.json").read_text())["detectorPolicy"]["limits"]


def test_missing_parser_dependencies_fail(tmp_path: Path) -> None:
    shutil.copytree(PACKAGE / "scripts", tmp_path / "scripts")
    target = tmp_path / "input.html"
    target.write_text("<p>Settings</p>")
    result = subprocess.run(
        ["node", str(tmp_path / "scripts/detect.mjs"), "--json", str(target)],
        cwd=tmp_path, text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Reinstall" in result.stderr
    assert not result.stdout
