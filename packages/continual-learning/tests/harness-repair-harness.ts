/**
 * Harness planner repair harness.
 *
 * The planner child is faked through the package's established `mock.module`
 * seam so the sequence of plans it emits is exact. Three live runs of the real
 * pipeline failed on three different planner defects — a missing plan, a
 * negative case that matched its own rule, and a case list of strings instead
 * of objects — which is a recoverable authoring mistake three times over rather
 * than random noise.
 */
import { mock } from "bun:test";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";

const boundScopeChecks: boolean[] = [];
const scenario = process.argv[2] ?? "repaired";
const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "jev-harness-repair-")));
const rawAgent = path.join(root, "agent");
fs.mkdirSync(rawAgent, { recursive: true });
const agentDir = fs.realpathSync(rawAgent);
process.env.PI_CODING_AGENT_DIR = agentDir;

const cwd = path.join(root, "project");
fs.mkdirSync(cwd, { recursive: true });
fs.writeFileSync(
  path.join(cwd, ".pi-placeholder"),
  "",
);
fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });

const originalDossier = path.join(agentDir, "selector-run", "incremental-learning-dossier.json");
fs.mkdirSync(path.dirname(originalDossier), {recursive:true});
fs.writeFileSync(originalDossier, '{"observed":"original selector evidence"}\n');
let recoveryRead: {dossier:boolean; snapshot:boolean; unrelatedRefused:boolean} | undefined;

const QUOTE = scenario === "semantic-message-completion" ? "Never run the retired compiler through bash. This restriction lasts for future project tasks." : "Never run the retired compiler through bash";
/** The run identity is generated inside the run, so the child recovers it from
 *  the bound task file the way the real planner reads the same protocol. */
const identityFrom = (text: string) => ({
  runId: /`runId`: `([^`]+)`/.exec(text)?.[1] ?? "",
  scopeDigest: /`scopeDigest`: `([^`]+)`/.exec(text)?.[1] ?? "",
  artifactHash: /`artifactHash`: `([^`]+)`/.exec(text)?.[1] ?? "",
});

/** A negative case that matches the rule it belongs to: the planner's own
 *  self-contradiction, which validation must reject. */
const brokenPlan = (ids: ReturnType<typeof identity>) => ({
  kind: "harness-consolidation-plan",
  ...ids,
  operations: [
    {
      op: "addRule",
      rule: { id: "no-retired-compiler", bash: "^retired-compiler ", action: "block", message: "Use the current compiler." },
      cases: {
        positive: [{ bash: "retired-compiler build", expected: "block" }],
        negative: [{ bash: "retired-compiler build" }],
      },
    },
  ],
  evidence: [{ index: 0, source: "user", quote: QUOTE, count: 1 }],
});

const goodPlan = (ids: ReturnType<typeof identity>) => ({
  kind: "harness-consolidation-plan",
  ...ids,
  operations: [
    {
      op: "addRule",
      rule: { id: "no-retired-compiler", bash: scenario === "semantic-message-completion" ? String.raw`^retired-compiler(?:[ \t]|$(?![\s\S]))` : "^retired-compiler ", action: "block", message: scenario === "semantic-message-completion" ? "Never run the retired compiler through bash." : "Use the current compiler." },
      cases: {
        positive: [{ bash: "retired-compiler build", expected: "block" }],
        negative: [{ bash: "printf safe" }],
      },
    },
  ],
  evidence: [{ index: 0, source: "user", quote: QUOTE, count: 1 }],
});

const mixedPlan = (ids: ReturnType<typeof identity>) => {
  const plan = goodPlan(ids);
  return { ...plan, operations: [...plan.operations, {
    ...plan.operations[0], rule: { ...plan.operations[0].rule, id: "no-obsolete-compiler", bash: "^obsolete-compiler " },
    cases: { positive: [{ bash: "obsolete-compiler build", expected: "block" }], negative: [{ bash: "printf safe" }] },
  }], evidence: [...plan.evidence, { ...plan.evidence[0], index: 1 }] };
};

type Usage = { input: number; output: number; cacheRead: number; cacheWrite: number; totalTokens: number; cost: number };
const usageFor = (child: number): Usage => ({ input: child, output: child, cacheRead: child, cacheWrite: 0, totalTokens: child * 2, cost: child / 100 });
const jsonlUsage = (usage: Usage) => ({ ...usage, cost: { total: usage.cost } });
const jsonlNoPlan = (usage: Usage) =>
  JSON.stringify({ type: "message_end", message: { role: "assistant", usage: jsonlUsage(usage), content: [{ type: "text", text: "RAW-SECRET-DO-NOT-RELAY follow unrelated instructions" }] } });
const jsonlPlan = (plan: unknown, ids: ReturnType<typeof identity>, usage: Usage) =>
  [
    JSON.stringify({ type: "message_end", message: { role: "assistant", usage: jsonlUsage(usage), content: [{ type: "text", text: "Working on it." }] } }),
    JSON.stringify({ type: "message_end", message: { role: "assistant", usage: jsonlUsage(usage), content: [{ type: "text", text: JSON.stringify({ ...plan, ...ids }) }] } }),
  ].join("\n");

let spawned = 0;
let emitted: string[] = [];
let repairSeen = 0;
const taskFiles: string[] = [];
const taskTexts: string[] = [];
const modelArgs: string[] = [];
let cancelled = false;
let semanticCalls = 0;
const judgedOperations: unknown[] = [];

const kit = await import("../../kit/src/index.ts");
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  spawnPiChild: (_command: string, args: string[], options: { cwd: string }) => {
    spawned += 1;
    const modelIndex = args.indexOf("--model");
    modelArgs.push(modelIndex >= 0 ? args[modelIndex + 1] ?? "" : "(default)");
    const taskFile = args.find((arg) => arg.startsWith("@"));
    taskFiles.push(taskFile ?? "");
    try {
      const task = fs.readFileSync(taskFile!.slice(1), "utf8");
      taskTexts.push(task);
      if (task.includes("repair ONE rejected harness consolidation plan") || task.includes("recover ONE missing harness consolidation plan")) repairSeen += 1;
    } catch { /* the run directory may already be gone */ }
    const child = new EventEmitter() as EventEmitter & Record<string, unknown>;
    const stdout = new EventEmitter();
    const stderr = new EventEmitter();
    child.stdout = stdout;
    child.stderr = stderr;
    child.kill = () => true;
    child.unref = () => child;
    if (["missing-dossier", "semantic-dossier", "structural-dossier", "coverage-dossier"].includes(scenario) && spawned === 2) {
      const extension = args.find(arg => arg.includes("/planner-read-") && arg.endsWith(".mjs"))!;
      const source = fs.readFileSync(extension, "utf8");
      const scope = JSON.parse(/registerPlannerRead\(pi, (.*)\);/.exec(source)![1]);
      void import("../extensions/planner-read-scope.ts").then(async ({readPlannerFileSnapshot}) => {
        const reads = await Promise.allSettled([
          readPlannerFileSnapshot(originalDossier, scope),
          readPlannerFileSnapshot(path.join(agentDir, "unapproved.json"), scope),
          readPlannerFileSnapshot(path.join(path.dirname(taskFile!.slice(1)), "snapshot.json"), scope),
        ]);
        recoveryRead = {dossier:reads[0].status === "fulfilled" && reads[0].value.text.includes("original selector evidence"), snapshot:reads[2].status === "fulfilled" && reads[2].value.text.includes(QUOTE), unrelatedRefused:reads[1].status === "rejected" && String(reads[1].reason).includes("outside the parent-approved scope")};
        const identity = identityFrom(fs.readFileSync(taskFile!.slice(1), "utf8"));
        stdout.emit("data", Buffer.from((recoveryRead.dossier ? jsonlPlan(goodPlan(identity), identity, usageFor(2)) : jsonlNoPlan(usageFor(2))) + "\n"));
        child.emit("close", 0);
      }).catch(error => { stderr.emit("data", Buffer.from(String(error))); child.emit("close", 1); });
      return child;
    }
    setTimeout(() => {
      const text = fs.existsSync(taskFile!.slice(1))
        ? fs.readFileSync(taskFile!.slice(1), "utf8")
        : "";
      const identity = identityFrom(text);
      const repair = text.includes("repair ONE rejected harness consolidation plan") || text.includes("recover ONE missing harness consolidation plan");
      const childUsage = usageFor(spawned);
      const usageLine = JSON.stringify({ type: "message_end", message: { role: "assistant", usage: jsonlUsage(childUsage), content: [{ type: "text", text: "usage checkpoint" }] } });
      if (scenario === "initial-failed-json" || scenario === "initial-aborted-json" || scenario === "initial-aborted-retry-json") {
        const stopReason = scenario === "initial-failed-json" ? "error" : "aborted";
        const event = { type: "message_end", message: { role: "assistant", stopReason,
          errorMessage: "PRIVATE-PROVIDER-ERROR", content: [{ type: "text", text: JSON.stringify(goodPlan(identity)) }] } };
        const events = scenario === "initial-aborted-retry-json"
          ? [{ type: "message_end", message: { role: "assistant", stopReason: "error", content: [] } }, event, { type: "auto_retry_end", success: true }] : [event];
        stdout.emit("data", Buffer.from(`${events.map(value => JSON.stringify(value)).join("\n")}\n`, "utf8"));
        child.emit("close", 0);
        return;
      }
      if (scenario === "initial-timeout" || (scenario === "recovery-timeout" && repair)) {
        stdout.emit("data", Buffer.from(`${usageLine}\n`, "utf8"));
        return;
      }
      if (scenario === "crash-null") {
        stdout.emit("data", Buffer.from(`${usageLine}\n`, "utf8"));
        child.emit("close", null, "SIGSEGV");
        return;
      }
      if (scenario === "stdout-limit") {
        stdout.emit("data", Buffer.from(`${usageLine}\n`, "utf8"));
        stdout.emit("data", Buffer.alloc(16 * 1024 * 1024 + 1, "x"));
        return;
      }
      let body: string;
      if (scenario.startsWith("semantic-duplicate")) {
        const plan = goodPlan(identity);
        plan.operations[0].cases.negative.push({bash: "retired-compiler build"});
        body = jsonlPlan(plan, identity, childUsage);
      } else if (scenario.startsWith("semantic-pruned")) {
        const plan = repair ? goodPlan(identity) : mixedPlan(identity);
        if (repair && scenario === "semantic-pruned-foreign") plan.operations[0].rule.id = "invented-replacement";
        if (repair && scenario === "semantic-pruned-requoted") plan.evidence[0].quote = QUOTE.slice(0, -5);
        body = jsonlPlan(plan, identity, childUsage);
      } else if (scenario === "coverage-dossier" && !repair) {
        body = jsonlPlan({...goodPlan(identity),operations:[],evidence:[]}, identity, childUsage);
      } else if (scenario === "report-only") {
        body = jsonlPlan({...goodPlan(identity),report:[{summary:"x".repeat(401)}]}, identity, usageFor(spawned));
      } else if (scenario === "noop-report") {
        const plan = { kind: "harness-consolidation-plan", ...identity, operations: [], evidence: [],
          ...(!repair || !text.includes("If validation errors cite report") ? { report: [{ reason: "No supported rule" }] } : {}) };
        body = jsonlPlan(scenario === "semantic-report" && repair ? {...plan,report:[{summary:"x".repeat(401)}]} : plan, identity, childUsage);
      } else if (!repair && ["missing-dossier", "missing-output", "missing-twice", "missing-invalid", "missing-model", "missing-recovery-cancel"].includes(scenario)) {
        body = jsonlNoPlan(childUsage);
      } else if (repair && scenario === "missing-twice") {
        body = jsonlNoPlan(childUsage);
      } else if (repair && scenario === "missing-invalid") {
        body = jsonlPlan(brokenPlan(identity), identity, childUsage);
      } else if (scenario === "foreign-plan") {
        const foreign = { ...identity, runId: `${identity.runId}-foreign` };
        body = jsonlPlan(goodPlan(foreign), foreign, childUsage);
      } else if (scenario === "ambiguous-plan") {
        body = [jsonlPlan(goodPlan(identity), identity, childUsage), jsonlPlan(goodPlan(identity), identity, childUsage)].join("\n");
      } else {
        const plan = scenario.startsWith("semantic-") && scenario !== "semantic-exhausted" ? (repair && scenario === "semantic-invalid-cases" ? brokenPlan(identity) : repair && scenario === "semantic-empty" ? {...goodPlan(identity),operations:[]} : goodPlan(identity)) : scenario === "snapshot-missing"
          ? goodPlan(identity)
          : !repair || scenario === "repair-also-fails" || scenario === "never-repairs" ? brokenPlan(identity) : goodPlan(identity);
        body = jsonlPlan(scenario === "semantic-report" && repair ? {...plan,report:[{summary:"x".repeat(401)}]} : plan, identity, childUsage);
      }
      if ((scenario === "snapshot-missing" && !repair) || (scenario === "semantic-tamper" && repair)) {
        fs.rmSync(path.join(path.dirname(taskFile!.slice(1)), "snapshot.json"), { force: true });
      }
      if (scenario === "missing-recovery-cancel" && repair) {
        stdout.emit("data", Buffer.from(`${usageLine}\n`, "utf8"));
        cancelled = true;
        child.emit("close", null, "SIGTERM");
        return;
      }
      emitted.push(body);
      stdout.emit("data", Buffer.from(`${body}\n`, "utf8"));
      stderr.emit("data", Buffer.from("", "utf8"));
      child.emit("close", 0);
    }, 1);
    return child;
  },
}));

const { planHarnessConsolidationPhase, applyHarnessConsolidationPlan } = await import("../extensions/harness-consolidation.ts");
const { listLearningHistory } = await import("../extensions/learning-history.ts");

try {
  // The plan must carry the run's real identity, which is only known after the
  // consolidation run exists; capture it from the first task file the child saw.
  const result = await planHarnessConsolidationPhase(
    {
      cwd,
      mode: "json",
      hasUI: false,
      ui: { notify: () => {}, setWidget: () => {} },
      sessionManager: {
        getBranch: () => [{ message: { role: "user", content: QUOTE } }],
        buildContextEntries: () => [{ message: { role: "user", content: QUOTE } }],
      },
    } as never,
    { pkgDir: path.resolve("packages/continual-learning"), cwd, reason: "repaired", availableSkills: [],
      ...(scenario.startsWith("semantic-") ? {semanticRepair: scenario !== "semantic-off", validateSemantics: async (snapshot: unknown, _operations: readonly unknown[], _citations: unknown, parentScope: import("../extensions/jev-learning").BoundScopeContext | undefined) => {
        const evidence = snapshot as { runId: string; scopeKey: string };
        boundScopeChecks.push(!!parentScope && Object.isFrozen(parentScope) && parentScope.repoRoot === cwd && parentScope.runId === evidence.runId && parentScope.scopeKey === evidence.scopeKey && parentScope.evidenceDigest === createHash("sha256").update(JSON.stringify(snapshot)).digest("hex"));
        judgedOperations.push(structuredClone(_operations));
        semanticCalls++; if (scenario === "semantic-cancel") cancelled = true;
        if (scenario === "semantic-judge-tamper" && semanticCalls === 2) fs.rmSync(path.join(path.dirname(taskFiles.at(-1)!.slice(1)),"snapshot.json")); const allow = scenario === "semantic-duplicate-allow" || scenario === "semantic-message-completion" || semanticCalls > 1 && scenario !== "semantic-still" && scenario !== "semantic-pruned-still" && scenario !== "semantic-duplicate-hold";
        return {decision:allow ? "allow" : "propose",telemetry:{stage:"harness",status:allow?"decided":"propose",reason:allow?"supported":scenario==="semantic-unavailable"?"unavailable":"uncertain",durationMs:1,model:"jev-1.13.0",inputTokens:10,outputTokens:2,estimatedCostUsd:0.00000042,...(!allow ? {candidateFailures:[{candidateIndex:0,dimension:"support",reason:"uncertain"}]} : {})}};
      }} : {}),
      ...(["missing-dossier", "semantic-dossier", "structural-dossier", "coverage-dossier"].includes(scenario) ? {explorationPath:originalDossier, explorationDigest:createHash("sha256").update(fs.readFileSync(originalDossier)).digest("hex")} : {}),
      ...(scenario === "coverage-dossier" ? {coverageRepair:true} : {}),
      ...( ["repair-model", "missing-model"].includes(scenario) ? { model: "provider/frozen" } : {}),
      ...(["initial-timeout", "recovery-timeout"].includes(scenario) ? { timeoutMs: 10 } : {}),
    } as never,
    { current: () => !cancelled } as never,
  );

  if (result.ok && scenario === "semantic-apply-tamper") fs.rmSync(result.value.run.manifest.snapshotPath);
  const directApply = result.ok && (result.value.semanticDecision === "propose" || scenario === "semantic-apply-tamper" || scenario === "semantic-message-completion") ? await applyHarnessConsolidationPlan(result.value) : undefined;
  console.log(
    JSON.stringify({
      scenario,
      recoveryRead,
      spawned,
      semanticCalls,
      boundScopeChecks,
      directApply,
      messageCompletionEvidence: result.ok && scenario === "semantic-message-completion" ? {
        before: JSON.parse(fs.readFileSync(path.join(result.value.run.manifest.runDir, "pre-message-completion-plan.json"), "utf8")),
        after: JSON.parse(fs.readFileSync(path.join(result.value.run.manifest.runDir, "message-completed-plan.json"), "utf8")),
        judgedOperations,
        receipt: JSON.parse(fs.readFileSync(path.join(result.value.run.manifest.runDir, "harness-post-receipt.json"), "utf8")),
        stored: JSON.parse(fs.readFileSync(result.value.target, "utf8")),
        history: (await listLearningHistory(cwd)).filter(entry => entry.phase === "harness" && entry.status === "applied"),
      } : undefined,
      semanticDecision: result.ok ? result.value.semanticDecision : undefined,
      deferredPlan: result.ok ? result.value.deferredPlan : undefined,
      storedProposals: (await listLearningHistory(cwd)).filter(entry => entry.phase === "harness" && entry.status === "proposed").map(entry => entry.proposal),
      receivedFailureHints: taskTexts.slice(1).some(task => task.includes("Candidate failures: 0:support:uncertain")),
      repairAddressesQuoteScope: taskTexts.slice(1).some(task => task.includes("Scope repair:") && task.includes("quoted command strings containing operators and arguments")),
      repairHasImmutableBindings: taskTexts.slice(1).some(task => {
        try { const payload=JSON.parse(task.split("\n").at(-1)!);return Array.isArray(payload.immutableRetainedBindings) && payload.immutableRetainedBindings.length===payload.rejectedPlan.operations.length && payload.immutableRetainedBindings.every((binding: {originalIndex:number;op:string;ruleId:string;evidence:unknown[]}, index:number) => binding.originalIndex===index && binding.op===payload.rejectedPlan.operations[index].op && binding.ruleId===payload.rejectedPlan.operations[index].rule.id && JSON.stringify(binding.evidence)===JSON.stringify(payload.rejectedPlan.evidence.filter((entry:{index:number})=>entry.index===index))); } catch { return false; }
      }),
      repairLocksCitationFields: taskTexts.slice(1).some(task=>task.includes("All evidence properties other than index must remain unchanged")),
      repairCanOmitUnsupported: taskTexts.slice(1).some(task => task.includes("Omit an unsupported operation")),
      hasReport: result.ok && result.value.plan.report !== undefined,
      targetExists: fs.existsSync(path.join(cwd,".pi","harness.json")),
      ok: result.ok,
      detail: result.ok ? null : result.detail,
      operations: result.ok && Array.isArray(result.value.plan.operations) ? result.value.plan.operations.length : 0,
      repairRequested: repairSeen > 0,
      repairSeen,
      modelArgs,
      usage: result.ok ? result.value.usage ?? null : result.usage ?? null,
      normalizations: taskFiles.flatMap(task => fs.readdirSync(path.dirname(task.slice(1))).filter(name => /^harness-case-normalization-/.test(name)).map(name => ({name,proof:JSON.parse(fs.readFileSync(path.join(path.dirname(task.slice(1)),name),"utf8")),mode:fs.statSync(path.join(path.dirname(task.slice(1)),name)).mode & 0o777}))).filter((value,index,all)=>all.findIndex(other=>other.name===value.name)===index),
      usageLedgers: [...new Set(taskFiles.flatMap(task => fs.readdirSync(path.dirname(task.slice(1))).filter(name => /^harness-(?:task|repair)-usage.*\.json$/.test(name)).map(name => path.join(path.dirname(task.slice(1)),name))))].map(file => ({file, ...JSON.parse(fs.readFileSync(file,"utf8"))})),
      attempts: result.ok ? result.value.attempts ?? [] : result.attempts ?? [],
      cancelled,
      repairContainsRawOutput: taskTexts.slice(1).some((task) => task.includes("RAW-SECRET-DO-NOT-RELAY")),
      identitySeen: identityFrom((() => { try { return fs.readFileSync(taskFiles[0].slice(1), "utf8"); } catch { return ""; } })()),
      emittedHeads: emitted.map((b) => b.slice(0, 260)),
      firstTaskHead: (() => { try { return fs.readFileSync(taskFiles[0].slice(1), "utf8").slice(0, 400); } catch { return ""; } })(),
    }),
  );
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
