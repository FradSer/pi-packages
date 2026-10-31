import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {test} from "node:test";
import {createHash} from "node:crypto";
import {selectedMemoryRelationClosures, MemoryRelationClosureError} from "../extensions/memory-relation-closure.ts";
import {materializeSourceExcerptPlan, assertSourceExcerptBindings, selectedProjectSourceObligations, sourceRoleOnlyRepairAdmitted, sourceRoleRangeChoices} from "../extensions/source-excerpt-memory.ts";
import {bindMemoryCitationAmendment, semanticMemoryRepairCandidates} from "../extensions/inject-memory.ts";
import {containsSensitiveMemoryMaterial} from "../extensions/consolidation-run.ts";

// Public p-limit 7.3.1 source from the retained V1 checkout. These tests exercise
// source/selection mechanics; no model or service judgment is replaced.
const implementation = fs.readFileSync(new URL("./fixtures/p-limit-wrapper-source.js", import.meta.url), "utf8");
const declaration = fs.readFileSync(new URL("./fixtures/p-limit-wrapper-source.d.ts", import.meta.url), "utf8");
function citation(text: string, index: number, start: string, end = start) {
  const a = text.indexOf(start), b = text.indexOf(end, a);
  assert.ok(a >= 0 && b >= a);
  const first = text.slice(0, a).split("\n").length;
  const last = text.slice(0, b + end.length).split("\n").length;
  return {ref: `e${index}.b0.l${first}`, ...(last === first ? {} : {endRef: `e${index}.b0.l${last}`})};
}
function fixture(js = implementation, user = "Inspect limitFunction and its clearQueue relationship to the internal limiter, using implementation and declaration.") {
  const cwd = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "memory-implementation-")));
  const pkg = JSON.stringify({type: "module", exports: {types: "./index.d.ts", default: "./index.js"}});
  for (const [name, text] of [["index.js", js], ["index.d.ts", declaration], ["package.json", pkg]]) fs.writeFileSync(path.join(cwd, name), text);
  const snapshot = {entries: [
    {role: "user", content: user},
    {role: "assistant", content: ["package.json", "index.js", "index.d.ts"].map((name, index) => ({type: "toolCall", id: `r${index}`, name: "read", arguments: {path: path.join(cwd, name), offset: 1, limit: 2000}}))},
    ...[pkg, js, declaration].map((content, index) => ({role: "toolResult", toolName: "read", toolCallId: `r${index}`, isError: false, content})),
  ]};
  const sourceCitations = [
    citation(js, 3, "export function limitFunction", "return (...arguments_) => limit(() => function_(...arguments_));"),
    citation(declaration, 4, "export function limitFunction", "): (...arguments_: Arguments) => Promise<ReturnType>;"),
    citation(declaration, 4, "export default function pLimit", "export default function pLimit(concurrency: number | Options): LimitFunction;"),
    citation(declaration, 4, "export type LimitFunction = {"),
    citation(declaration, 4, "clearQueue: () => void;"),
  ];
  const knowledge = {sourceCitations, units: [{text: "The inspected limitFunction creates an internal pLimit result and returns a separate callable. The declared LimitFunction has clearQueue; the wrapper declaration is a plain callable. This records inspected source, not executed cancellation or scheduler behavior.", citationIndexes: [0, 1, 2, 3, 4]}]};
  const plan = {operations: [], newMemories: [{name: "wrapper.md", kind: "project", classification: "private", description: "Observed wrapper and internal limiter interface.", knowledge}]};
  return {cwd, snapshot, knowledge, plan, run: {manifest: {cwd}}, close: () => fs.rmSync(cwd, {recursive: true, force: true})};
}
function selectImplementation(f: ReturnType<typeof fixture>) {
  const js = (f.snapshot.entries[3] as any).content;
  f.knowledge.sourceCitations[0] = citation(js, 3, "const generator =", "return (...arguments_) => limit(() => function_(...arguments_));");
  f.knowledge.units[0].citationIndexes.push(f.knowledge.sourceCitations.length);
  f.knowledge.sourceCitations.push(citation(js, 3, "export default function pLimit(concurrency) {"));
}

test("the real omitted internal receiver definition and return require explicit used source roles", () => {
  const f = fixture();
  try {
    assert.throws(() => selectedMemoryRelationClosures(f.snapshot, f.knowledge, f.cwd), (error: any) => error instanceof MemoryRelationClosureError && /implementation-member-definition/.test(error.message) && /implementation-return/.test(error.message));
  } finally {f.close();}
});

test("selected implementation roles retain a readable source-only relationship and exact source bindings", async () => {
  const f = fixture();
  try {
    selectImplementation(f);
    const out: any = await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true});
    const body = out.newMemories[0].content;
    assert.match(body, /Observed implementation syntax from "index\.js" \(source observation only\)/);
    assert.ok(body.includes("`pLimit` declares callable `generator`, contains `Object.defineProperties(generator, …)` with `clearQueue`, and returns `generator`"));
    assert.ok(body.includes("clearQueue: {"));
    assert.ok(body.includes("return generator;"));
    assert.equal(body.includes("map: {"), false);
    assert.equal(out.newMemories[0].evidence.length, 6);
    assert.ok(body.includes(f.knowledge.units[0].text));
    await assertSourceExcerptBindings(f.run);
    fs.writeFileSync(path.join(f.cwd, "index.js"), implementation.replace("let activeCount = 0;", "let activeCount = 1;"));
    await assert.rejects(assertSourceExcerptBindings(f.run));
  } finally {f.close();}
});

test("the bound structural correction cannot drop or merely stop using implementation roles", () => {
  const f = fixture();
  try {
    let obligations: any;
    assert.throws(() => selectedMemoryRelationClosures(f.snapshot, f.knowledge, f.cwd, undefined, value => {obligations = value;}));
    assert.ok(obligations);
    selectImplementation(f);
    assert.equal(selectedMemoryRelationClosures(f.snapshot, f.knowledge, f.cwd, obligations).length, 1);
    f.knowledge.units[0].citationIndexes = [1, 2, 3, 4];
    assert.throws(() => selectedMemoryRelationClosures(f.snapshot, f.knowledge, f.cwd, obligations), /implementation/);
  } finally {f.close();}
});

for (const [name, transform] of Object.entries({
  "shadowed Object parameter": (js: string) => js.replace("pLimit(concurrency)", "pLimit(concurrency, Object)"),
  "shadowed Object binding": (js: string) => "const Object = other;\n" + js,
  "Object descriptor deletion": (js: string) => js + "\ndelete Object.defineProperties;\n",
  "Object descriptor mutation call": (js: string) => js + "\nObject.defineProperty(Object, 'defineProperties', {value: other});\n",
  "global Object descriptor mutation": (js: string) => js + "\nglobalThis.Object.defineProperties = other;\n",
  "mutable receiver": (js: string) => js.replace("const generator =", "let generator ="),
  "receiver assignment": (js: string) => js.replace("\treturn generator;", "\tgenerator = other;\n\treturn generator;"),
  "receiver property assignment": (js: string) => js.replace("\treturn generator;", "\tgenerator.clearQueue = other;\n\treturn generator;"),
  "receiver alias": (js: string) => js.replace("\tObject.defineProperties(generator, {", "\tconst alias = generator;\n\tObject.defineProperties(generator, {"),
  "receiver passed to an unknown mutator": (js: string) => js.replace("\treturn generator;", "\tmutate(generator);\n\treturn generator;"),
  "different returned object": (js: string) => js.replace("\treturn generator;", "\treturn other;"),
  "multiple returns": (js: string) => js.replace("\treturn generator;", "\tif (flag) return generator;\n\treturn generator;"),
  "conditional definition": (js: string) => js.replace("\tObject.defineProperties(generator, {", "\tif (flag) { Object.defineProperties(generator, {").replace("\t});\n\n\treturn generator;", "\t}); }\n\n\treturn generator;"),
  "computed member": (js: string) => js.replace("clearQueue: {", "['clearQueue']: {"),
  "spread descriptor": (js: string) => js.replace("\tObject.defineProperties(generator, {", "\tObject.defineProperties(generator, {\n\t\t...other,"),
  "duplicate descriptor": (js: string) => js.replace("\t\tclearQueue: {", "\t\tclearQueue: {value() {}},\n\t\tclearQueue: {"),
})) {
  test(`${name} cannot manufacture an implementation relationship`, () => {
    const f = fixture(transform(implementation));
    try {
      const relations = selectedMemoryRelationClosures(f.snapshot, f.knowledge, f.cwd);
      assert.ok(relations.every(relation => relation.implementation === undefined));
    } finally {f.close();}
  });
}

test("unrelated user topics and declaration-only implementations retain prior behavior", () => {
  const unrelated = fixture(implementation, "Inspect the startup cache only.");
  const direct = fixture("export default function pLimit(concurrency) { return {}; }\n" + implementation.slice(implementation.indexOf("export function limitFunction")));
  try {
    assert.deepEqual(selectedMemoryRelationClosures(unrelated.snapshot, unrelated.knowledge, unrelated.cwd), []);
    const relations = selectedMemoryRelationClosures(direct.snapshot, direct.knowledge, direct.cwd);
    assert.equal(relations.length, 1);
    assert.equal(relations[0].implementation, undefined);
  } finally {unrelated.close();direct.close();}
});

test("legacy atomic declaration selection cannot discard a selected implementation binding", async () => {
  const f = fixture();
  try {
    selectImplementation(f);
    f.knowledge.units.push({kind: "declared-api-relation", factory: f.knowledge.sourceCitations[2], owner: f.knowledge.sourceCitations[3], member: f.knowledge.sourceCitations[4]} as any);
    const out: any = await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true});
    assert.match(out.newMemories[0].content, /Observed implementation syntax/);
    assert.ok(out.newMemories[0].content.includes("return generator;"));
  } finally {f.close();}
});

test("an unchanged selected JS quote cannot hide another same-file source change", async () => {
  const f = fixture();
  try {
    selectImplementation(f);
    fs.writeFileSync(path.join(f.cwd, "index.js"), implementation.replace("let activeCount = 0;", "let activeCount = 1;"));
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}));
  } finally {f.close();}
});

test("a source symlink cannot supply implementation roles", async () => {
  const f = fixture();
  try {
    selectImplementation(f);
    fs.renameSync(path.join(f.cwd, "index.js"), path.join(f.cwd, "actual.js"));
    fs.symlinkSync("actual.js", path.join(f.cwd, "index.js"));
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}));
  } finally {f.close();}
});

test("implementation retention cannot increase the original citation or body-unit limits", async () => {
  const f = fixture();
  try {
    selectImplementation(f);
    while (f.knowledge.sourceCitations.length < 9) f.knowledge.sourceCitations.push({ref: "e0.b0.l1"});
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}), /1\.\.8/);
    f.knowledge.sourceCitations.length = 6;
    while (f.knowledge.units.length < 32) f.knowledge.units.push(structuredClone(f.knowledge.units[0]));
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}), /1\.\.32/);
  } finally {f.close();}
});

test("source-role-only repair keeps original text while public obligations contain no private AST coordinates", async () => {
  const f = fixture();
  try {
    const digest = createHash("sha256").update(JSON.stringify(f.snapshot)).digest("hex");
    const identity = {runId: "source-role-fixture", scopeKey: "fixture", scopeDigest: "a".repeat(64), snapshotDigest: digest};
    Object.assign(f.run.manifest, identity);
    Object.assign(f.plan, identity, {kind: "incremental-memory-plan", schemaVersion: 1, version: 1, artifactHash: digest});
    const originalText = f.knowledge.units.map(unit => unit.text);
    let rejection: any;
    try {await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true});}
    catch (error) {rejection = error;}
    assert.ok(rejection instanceof MemoryRelationClosureError);
    assert.equal(sourceRoleOnlyRepairAdmitted(f.run, f.plan, f.snapshot, rejection), true);
    const publicValue = selectedProjectSourceObligations(f.run);
    assert.equal(JSON.stringify(publicValue).includes("sourceSpan"), false);
    assert.equal(JSON.stringify(rejection.obligations).includes("sourceSpan"), true);
    selectImplementation(f);
    const out: any = await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true});
    assert.deepEqual(f.knowledge.units.map(unit => unit.text), originalText);
    for (const text of originalText) assert.ok(out.newMemories[0].content.includes(text));
    assert.match(out.newMemories[0].content, /Observed implementation syntax/);
  } finally {f.close();}
});

test("an explicit model-selected catalog can retain the complete relation within eight citations", async () => {
  const f = fixture(implementation, "Inspect limitFunction and clearQueue together.\nSource observations do not prove execution.\nInspect the original source only.\nDo not infer cancellation.");
  try {
    selectImplementation(f);
    for (const line of [2, 3, 4]) {
      f.knowledge.units[0].citationIndexes.push(f.knowledge.sourceCitations.length);
      f.knowledge.sourceCitations.push({ref: `e0.b0.l${line}`});
    }
    assert.equal(f.knowledge.sourceCitations.length, 9);
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}), /1\.\.8/);
    // This change represents the producer's explicit selection; the parent never
    // merges references or trims a catalog to manufacture acceptance.
    f.knowledge.sourceCitations[3] = citation(declaration, 4, "export type LimitFunction = {", "clearQueue: () => void;");
    f.knowledge.sourceCitations.splice(4, 1);
    f.knowledge.units[0].citationIndexes = [...new Set(f.knowledge.units[0].citationIndexes.map(index => index === 4 ? 3 : index > 4 ? index - 1 : index))];
    const out: any = await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true});
    assert.equal(f.knowledge.sourceCitations.length, 8);
    assert.equal(out.newMemories[0].evidence.length, 8);
    assert.match(out.newMemories[0].content, /Observed implementation syntax/);
    assert.equal(out.newMemories[0].content.includes("Note: This does not cancel"), false);
  } finally {f.close();}
});

test("parent-bound learning_read roles use their original audit paths, complete hashes and pairing", async () => {
  const f = fixture();
  try {
    const hash = (value: string) => createHash("sha256").update(value).digest("hex");
    for (const call of (f.snapshot.entries[1] as any).content) call.name = "learning_read";
    for (let index = 2; index < f.snapshot.entries.length; index++) {
      const entry: any = f.snapshot.entries[index];
      const source = entry.content;
      entry.toolName = "learning_read";
      entry.details = {sourcePath: (f.snapshot.entries[1] as any).content[index - 2].arguments.path,
        sourceSha256: hash(source), readOnlyMaintenanceAudit: true};
      const lines = source.split("\n").length;
      entry.content = `${source}\n[lines 1-${lines} of ${lines}]`;
    }
    const audit = {evidenceDigest: hash(JSON.stringify(f.snapshot)), requireAudit: true,
      entryDigests: f.snapshot.entries.slice(1).map(entry => hash(JSON.stringify(entry)))};
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, audit, {retainSelectedDeclarations: true}), /implementation/);
    selectImplementation(f);
    const out: any = await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, audit, {retainSelectedDeclarations: true});
    assert.match(out.newMemories[0].content, /Observed implementation syntax/);
    await assert.rejects(materializeSourceExcerptPlan({manifest: {cwd: f.cwd}}, f.plan, f.snapshot,
      {...audit, entryDigests: audit.entryDigests.slice(1)}, {retainSelectedDeclarations: true}));
  } finally {f.close();}
});

function supportRepairFixture() {
  const f = fixture();
  const example = "const receiver = limitFunction(async value => value, {concurrency: 1});\nconsole.log(receiver.clearQueue);\n";
  const examplePath = path.join(f.cwd, "example.js");
  fs.writeFileSync(examplePath, example);
  f.snapshot.entries.push({role: "assistant", content: [{type: "toolCall", id: "example", name: "read", arguments: {path: examplePath, offset: 1, limit: 2000}}]} as any,
    {role: "toolResult", toolName: "read", toolCallId: "example", isError: false, content: example} as any);
  f.knowledge.sourceCitations.push({ref: "e6.b0.l1", endRef: "e6.b0.l2"});
  f.knowledge.units.push({text: "The inspected example prints the returned receiver's clearQueue property.", citationIndexes: [5]});
  const identity = {runId: "support-fixture", scopeKey: "scope", scopeDigest: "s", artifactHash: "a", snapshotDigest: "h"};
  Object.assign(f.plan, {kind: "incremental-memory-plan", version: 1, schemaVersion: 1, ...identity});
  const candidateId = semanticMemoryRepairCandidates(f.plan)[0].candidateId;
  const amendment = (evidence: unknown[], mappings: number[][]) => ({kind: "incremental-memory-amendment", version: 1, ...identity,
    replacements: [{candidateId, evidence, units: mappings.map((citationIndexes, index) => ({unitId: `unit:${index}`, citationIndexes}))}]});
  return {...f, identity, amendment, context: {snapshot: f.snapshot, cwd: f.cwd}};
}

test("the real source-role repair shape cannot replace an example's support with every unrelated role", () => {
  const f = supportRepairFixture();
  try {
    const evidence = [...f.knowledge.sourceCitations.slice(0, 5),
      citation(implementation, 3, "export default function pLimit(concurrency) {"),
      citation(implementation, 3, "Object.defineProperties(generator, {"),
      citation(implementation, 3, "return generator;")];
    assert.equal(evidence.length, 8);
    assert.throws(() => (bindMemoryCitationAmendment as any)(f.plan, f.amendment(evidence, [evidence.map((_, index) => index), evidence.map((_, index) => index)]),
      f.identity, undefined, ["unit:0", "unit:1"], f.context), /support|source/i);
  } finally {f.close();}
});

test("retaining an original reference elsewhere cannot remove it from its own frozen unit", () => {
  const f = supportRepairFixture();
  try {
    assert.throws(() => (bindMemoryCitationAmendment as any)(f.plan,
      f.amendment(f.knowledge.sourceCitations, [[0, 1, 2, 3, 4, 5], [0]]), f.identity, undefined, ["unit:0", "unit:1"], f.context), /support|source/i);
  } finally {f.close();}
});

test("source-role repair accepts explicit containing ranges while preserving frozen text", () => {
  const f = supportRepairFixture();
  try {
    const evidence = [...f.knowledge.sourceCitations];
    evidence[0] = citation(implementation, 3, "const generator =", "return (...arguments_) => limit(() => function_(...arguments_));");
    const out: any = (bindMemoryCitationAmendment as any)(f.plan, f.amendment(evidence, [[0, 1, 2, 3, 4], [5]]),
      f.identity, undefined, ["unit:0", "unit:1"], f.context);
    assert.deepEqual(out.newMemories[0].knowledge.units.map((unit: any) => unit.text), f.knowledge.units.map(unit => unit.text));
    assert.deepEqual(out.newMemories[0].knowledge.sourceCitations, evidence);
    assert.throws(() => (bindMemoryCitationAmendment as any)(f.plan, f.amendment(evidence, [[0, 1, 2, 3, 4], [5]]),
      f.identity, undefined, ["unit:0", "unit:1"]), /context/);
  } finally {f.close();}
});

for (const kind of ["same-source", "different-path", "changed-source", "unpaired", "different-block", "partial-range"]) {
  test(`a ${kind} source reference ${kind === "same-source" ? "can" : "cannot"} replace a unit's original support`, () => {
    const f = supportRepairFixture();
    try {
      const prior: any = f.snapshot.entries[6], oldText = prior.content;
      let next: any = {ref: "e8.b0.l1", endRef: "e8.b0.l2"};
      if (kind === "different-block") {
        prior.content = [{type: "text", text: oldText}, {type: "text", text: oldText}];
        next = {ref: "e6.b1.l1", endRef: "e6.b1.l2"};
      } else if (kind === "partial-range") next = {ref: "e6.b0.l2"};
      else {
        const file = kind === "different-path" ? path.join(f.cwd, "other.js") : path.join(f.cwd, "example.js");
        f.snapshot.entries.push({role: "assistant", content: [{type: "toolCall", id: "alias", name: "read", arguments: {path: file, offset: 1, limit: 2000}}]} as any,
          {role: "toolResult", toolName: "read", toolCallId: kind === "unpaired" ? "missing" : "alias", isError: false,
            content: oldText + (kind === "changed-source" ? "// changed revision\n" : "")} as any);
      }
      const evidence = [...f.knowledge.sourceCitations];evidence[5] = next;
      const bind = () => (bindMemoryCitationAmendment as any)(f.plan, f.amendment(evidence, [[0, 1, 2, 3, 4], [5]]),
        f.identity, undefined, ["unit:0", "unit:1"], f.context);
      if (kind === "same-source") assert.ok(bind());
      else assert.throws(bind, /support|source/i);
    } finally {f.close();}
  });
}

async function captureRangeChoices(f: ReturnType<typeof fixture>) {
  await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}), /relation/);
  return sourceRoleRangeChoices(f.run, "wrapper.md", f.knowledge, f.snapshot);
}

test("bounded range data suggests adjacent roles without editing or selecting the producer catalog", async () => {
  const f = fixture();
  try {
    const before = JSON.stringify(f.plan), choices = await captureRangeChoices(f);
    assert.ok(choices.length > 0 && choices.length <= 4);
    assert.ok(choices.some(choice => JSON.stringify({ref: choice.ref, endRef: choice.endRef}) === JSON.stringify(citation(implementation, 3, "const generator =", "return (...arguments_) => limit(() => function_(...arguments_));"))));
    assert.ok(choices.some(choice => JSON.stringify({ref: choice.ref, endRef: choice.endRef}) === JSON.stringify(citation(declaration, 4, "export default function pLimit", "): (...arguments_: Arguments) => Promise<ReturnType>;"))));
    assert.ok(choices.every(choice => choice.utf16Length <= 2000 && choice.coversRoles.length + choice.coversOriginalSupports.length >= 2));
    assert.equal(JSON.stringify(choices).includes("text"), false);
    assert.equal(JSON.stringify(choices).includes("sourceSpan"), false);
    assert.equal(JSON.stringify(f.plan), before);
    assert.equal(choices.some(choice => choice.ref === "e3.b0.l3" && choice.endRef === "e3.b0.l68"), false);
    // Hints never satisfy the missing explicit producer selections.
    await assert.rejects(materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true}), /implementation/);
  } finally {f.close();}
});

test("range data rejects current full-source changes even outside the offered spans", async () => {
  const f = fixture();
  try {
    await captureRangeChoices(f);
    fs.writeFileSync(path.join(f.cwd, "index.js"), implementation.replace("let activeCount = 0;", "let activeCount = 1;"));
    await assert.rejects(sourceRoleRangeChoices(f.run, "wrapper.md", f.knowledge, f.snapshot), /source changed/);
    const changed = structuredClone(f.snapshot);(changed.entries[0] as any).content += " changed";
    await assert.rejects(sourceRoleRangeChoices(f.run, "wrapper.md", f.knowledge, changed), /snapshot changed/);
  } finally {f.close();}
});

test("range data never offers a sensitive or overlong continuous source interval", async () => {
  const unsafe = "// token: sk-test-secret\n";
  assert.equal(containsSensitiveMemoryMaterial(unsafe), true);
  for (const added of [unsafe, "// " + "x".repeat(2500) + "\n"]) {
    const js = implementation.replace("\tObject.defineProperties(generator, {", added + "\tObject.defineProperties(generator, {");
    const f = fixture(js);
    try {
      const choices = await captureRangeChoices(f), text = js.split("\n");
      assert.ok(choices.every(choice => choice.utf16Length <= 2000));
      for (const choice of choices.filter(choice => choice.ref.startsWith("e3."))) {
        const first = Number(/\.l(\d+)$/.exec(choice.ref)![1]), last = Number(/\.l(\d+)$/.exec(choice.endRef ?? choice.ref)![1]);
        const selected = text.slice(first - 1, last).join("\n");
        assert.ok(selected.length <= 2000);
        assert.equal(containsSensitiveMemoryMaterial(selected), false);
      }
      assert.equal(JSON.stringify(choices).includes("sk-test-secret"), false);
    } finally {f.close();}
  }
});

test("range data is absent without parent-captured complete-source obligations", async () => {
  const f = fixture();
  try {
    assert.deepEqual(await sourceRoleRangeChoices(f.run, "wrapper.md", f.knowledge, f.snapshot), []);
    (f.snapshot.entries[1] as any).content[1].arguments.offset = 2;
    await materializeSourceExcerptPlan(f.run, f.plan, f.snapshot, undefined, {retainSelectedDeclarations: true});
    assert.deepEqual(await sourceRoleRangeChoices(f.run, "wrapper.md", f.knowledge, f.snapshot), []);
  } finally {f.close();}
});
