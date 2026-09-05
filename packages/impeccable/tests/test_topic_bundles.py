from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def test_all_canonical_reference_links_are_reachable() -> None:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input='''
import assert from "node:assert/strict";
import { resolver } from "./packages/impeccable/src/resolver.ts";
import { catalog } from "./packages/impeccable/src/catalog.ts";
const references = new Set(catalog.filter(entry => entry.kind === "reference").map(entry => entry.id));
const failures = [];
for (const capability of resolver.capabilities) {
  const actor = capability.invocation === "user" ? "user" : "model";
  const queue = [resolver.load(capability.id, actor)];
  const visited = new Set();
  while (queue.length) {
    const bundle = queue.shift();
    for (const match of bundle.content.matchAll(/\\]\\(impeccable:([a-z][a-z0-9-]*)(?:#[^)]*)?\\)/g)) {
      const reference = match[1];
      if (!references.has(reference) || visited.has(reference)) continue;
      visited.add(reference);
      try {
        queue.push(resolver.load(capability.id, actor, reference));
      } catch (error) {
        failures.push(`${capability.id} via ${bundle.root} -> ${reference}: ${error.message}`);
      }
    }
    assert.ok(visited.size <= references.size);
  }
}
assert.deepEqual(failures, []);
''',
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_focused_refinement_topic_bundles() -> None:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input='''
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
''',
    )
    assert result.returncode == 0, result.stdout + result.stderr
