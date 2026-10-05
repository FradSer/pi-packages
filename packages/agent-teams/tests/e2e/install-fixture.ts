/**
 * One fixture, four install combinations.
 *
 * The combination is data: `PI_E2E_PACKAGES` names the local packages whose
 * extension entries this process is an install of, and the fixture loads exactly
 * those. A suite that wanted a tool from a package it did not list could not get
 * it, which is what makes "installed alone" mean something.
 *
 * A bundle lists its dependencies in its manifest, so a bundle combination
 * resolves to three loaded entries while a single-package combination resolves to
 * one. That difference is the bundle's whole claim, and it is derived from the
 * manifests on the harness side rather than declared here.
 *
 * Scenario scripts call the real tools. An argument of the form `$prev.path` is
 * read out of the previous tool result, so a task id that a create call returned is
 * the same id a later call acts on rather than a literal a test hard-coded.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installScriptedProvider, type ScriptedTurn } from "../../../../tests/e2e/support/scripted.ts";

const SCENARIO = process.env.PI_E2E_SCENARIO ?? "surface";
const PROBE = process.env.PI_E2E_PROBE ?? "e2e_probe";

/** The pending, resource-bearing task the seeded peer makes a conflict on. */
const PEER_RESOURCE_TASK = "toolchain-refresh";

const SURFACE: ScriptedTurn[] = [{ tool: PROBE, args: {} }];

/**
 * A child session's whole life, through the tool surface only.
 *
 * Every start takes a prompt, so this exercises the shape the intent contract
 * actually has: the child receives real work and answers. Nothing here waits for
 * that answer, so the roster facts this suite asserts are the synchronous ones a
 * start receipt already carries. A temporary label is display only, so the child
 * name the receipts carry is the generated one; the assertions follow the receipt
 * instead of predicting it.
 */
const AGENT_LIFECYCLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "agent_start", args: { label: "scout", prompt: "Read the evidence you are given and report what it shows.", tools: [] } },
  { tool: "agent_list", args: {} },
  { tool: "agent_inspect", args: { session: "$prev.session" } },
  { tool: "agent_stop", args: { session: "$prev.session" } },
];

// The fixture user authors agent.md before Pi starts. No tool invocation creates
// or promotes a definition. Fork writes private history; the next incarnation
// must really resume it while retaining the project cwd.
const SAVED_AGENT_LIFECYCLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "agent_list", args: {} },
  { tool: "agent_start", args: { identity: "saved-scout", prompt: "Read the supplied evidence.", fork: true } },
  { tool: "agent_list", args: {} },
  { tool: "agent_stop", args: { session: "$prev.session" } },
  { tool: "agent_list", args: {} },
  { tool: "agent_start", args: { identity: "saved-scout", prompt: "Read the supplied evidence again." } },
  { tool: "agent_inspect", args: { session: "$prev.session" } },
  { tool: "agent_stop", args: { session: "$prev.session" } },
  { tool: "agent_list", args: {} },
];

const OFFLINE_AGENT: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "agent_list", args: {} },
];

/** create → take → complete, across the tools that perform each step. */
const TASK_LIFECYCLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "create_task", args: { subject: "Ship the release" } },
  { tool: "list_tasks", args: { claimable: true } },
  { tool: "update_task", args: { id: "$prev.id", status: "in_progress" } },
  { tool: "update_task", args: { id: "$prev.id", status: "completed", outcome: "success", result: "released" } },
  { tool: "list_tasks", args: {} },
];

/**
 * A task set with more than one participant, and a take refused for overlap.
 *
 * The resident joins through `agent start`, which is the shape a team depends on: a
 * child with no prompt enters the pool and waits for work. The peer already holds
 * the toolchain, so taking a task that needs it must be refused, and the refusal
 * has to name the holder — a refusal that did not say who blocked you is a dead
 * end rather than a conflict.
 *
 * This is the mechanism a resident's self-serve take relies on: whoever acts holds
 * the task, and two participants cannot hold overlapping resources at once. The
 * resident's own process-level take travels as an intent file, which the leader
 * applies through the same store call the `task` tool makes here.
 */
/**
 * A resident joins, its leader takes work, and an overlapping take is refused.
 *
 * `create_task` no longer takes resource tags from the model, so the overlap is
 * staged the way a real coordination run has it: a resource-bearing task the peer
 * already holds through its own assignment. Whoever acts on that task has to be
 * refused, and the refusal has to name the holder — a refusal that did not say who
 * blocked you is a dead end rather than a conflict.
 *
 * This is the mechanism a resident's self-serve take relies on: whoever acts holds
 * the task, and two participants cannot hold overlapping resources at once. The
 * resident's own process-level take travels as an intent file, which the leader
 * applies through the same store call the `update_task` tool makes here.
 */
const RESIDENT_TAKES: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "agent_start", args: { label: "scout", prompt: "Wait for the work the leader hands you.", tools: [] } },
  { tool: "create_task", args: { subject: "Rewrite the parser" } },
  { tool: "list_tasks", args: { claimable: true } },
  { tool: "update_task", args: { id: "$prev.id", status: "in_progress" } },
  { tool: "update_task", args: { id: PEER_RESOURCE_TASK, status: "in_progress" } },
  { tool: "list_tasks", args: {} },
];

/**
 * All three packages, and a message that reaches a live peer.
 *
 * The recipient is the resident this scenario started, addressed by the exact
 * session route the start receipt returned, so the assertion is that a request was
 * routed to a real participant rather than that the tool existed. A bogus
 * recipient would only prove the tool refuses.
 */
const BUNDLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  // Started with a prompt, which is what gives the resident an open assignment. Mail
  // is work-bound: a message to a participant holding nothing is refused, and that
  // refusal is correct rather than a delivery failure. The route comes from the
  // receipt directly above it, so the message names the child that really exists.
  { tool: "agent_start", args: { label: "scout", prompt: "Audit the parser changes" } },
  { tool: "message", args: { to: "$prev.session", body: "Take the parser first", kind: "request" } },
  { tool: "create_task", args: { subject: "Coordinate the release" } },
  { tool: "update_task", args: { id: "$prev.id", status: "in_progress" } },
  // The scenario settles the task it created before it ends. A run that leaves
  // unfinished work makes the task reminder request a continuation, and a
  // settlement handler that returns a result on the settle that ends the run
  // leaves `pi --print` with nothing to print: the exit is clean and stdout is
  // empty, so the report this suite reads never arrives. That interaction is a
  // separate defect tracked on its own; a scenario about bundle kickoff has no
  // reason to depend on it, and every assertion below is unaffected.
  { tool: "update_task", args: { id: "$prev.id", status: "completed", outcome: "success", result: "The release coordinator is set" } },
  // An identity with no saved definition. The intent tool refuses it before any
  // spawn, because a label only names the display and cannot select a role. A
  // label the caller invented would succeed instead, and that difference is what
  // proves identity selection is real rather than decorative.
  { tool: "agent_start", args: { identity: "no-such-role-here", prompt: "Start anyway" } },
];

/**
 * The negative control: the two tools the tasks install cannot provide.
 *
 * Every argument is a literal on purpose. A cross-call placeholder would be
 * unresolvable here — the start it reads from never succeeded — and the harness
 * would stop the run before the second refusal was ever attempted.
 */
const ABSENT_TOOLS: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "create_task", args: { subject: "Prove the process is live" } },
  { tool: "agent_start", args: { label: "absent-scout", prompt: "Start anyway" } },
  { tool: "message", args: { to: "scout", body: "Take the parser first", kind: "request" } },
];

const SCENARIOS: Record<string, ScriptedTurn[]> = {
  surface: SURFACE,
  "agent-lifecycle": AGENT_LIFECYCLE,
  "saved-agent-lifecycle": SAVED_AGENT_LIFECYCLE,
  "offline-agent": OFFLINE_AGENT,
  "tasks-lifecycle": TASK_LIFECYCLE,
  "resident-takes": RESIDENT_TAKES,
  bundle: BUNDLE,
  "absent-tools": ABSENT_TOOLS,
};
for (const parameter of ["persistent", "memory", "worktree"]) {
  for (const value of [false, true]) {
    SCENARIOS[`removed-${parameter}-${value}`] = [
      { tool: PROBE, args: {} },
      { tool: "agent_start", args: { label: "removed-control", prompt: "Do not run", [parameter]: value } },
    ];
  }
}

/**
 * Seed a second participant that already holds the toolchain.
 *
 * Only when the combination includes a task set. The point is that the refusal a
 * suite asserts is produced by the real conflict check rather than staged: the peer
 * is on the roster, its holding is a real assignment, and the overlap is real.
 *
 * The roster entry is written at load time because the subagents package publishes
 * the participant registry on its own `session_start`, and a peer added after that
 * would be a participant the tasks never learn about. The tasks are written later,
 * because the tasks extension clears its store on `session_start` and reads the
 * session file back; a task seeded before that would simply vanish.
 */
async function seedSecondParticipant(pi: ExtensionAPI): Promise<void> {
  if (process.env.PI_E2E_HOST !== "peer") return;
  const { registerAgent } = await import("@fradser/pi-subagents");
  const { createTask, takeTask } = await import("@fradser/pi-tasks");
  registerAgent({
    name: "peer",
    role: "peer",
    spawnId: "e2e-peer",
    pid: 0,
    status: "working",
    currentTaskId: "peer-toolchain",
    assignment: { id: "task:peer", kind: "task", resources: ["toolchain"] },
    createdAt: 1,
    updatedAt: 1,
  });
  pi.on("session_start", () => {
    // A real task and a real take, so the holding the conflict check looks for is
    // one the tasks actually recorded. Seeding the roster entry alone would leave
    // the two disagreeing, and the check would walk a roster that knows nothing
    // about it.
    createTask({ id: "peer-toolchain", subject: "Hold the toolchain", resources: ["toolchain"] });
    const taken = takeTask("peer-toolchain", "peer");
    if (!taken.ok) throw new Error(`could not seed the peer holding: ${taken.reason}`);
    // The task a model-facing take collides with: the same resource tag, still
    // pending, so the conflict check runs instead of the held-by-other check.
    createTask({ id: PEER_RESOURCE_TASK, subject: "Refresh the toolchain", resources: ["toolchain"] });
  });
}

const packages = (process.env.PI_E2E_PACKAGES ?? "")
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);

export default async function e2eInstall(pi: ExtensionAPI): Promise<void> {
  for (const name of packages) {
    // Loaded by absolute specifier so the suite's temporary agent directory and the
    // repository's own package resolution cannot disagree about which copy runs.
    // Resolved by package name through this package's dependencies, which is how a
    // real install resolves it. A leaf reached by a relative path is a second
    // module instance, and a registration made in it would never be read.
    const entry = name === "agent-teams"
      ? new URL("../../index.ts", import.meta.url).href
      : import.meta.resolve(`@fradser/pi-${name}`);
    const loaded = (await import(entry)) as {
      default?: (api: ExtensionAPI) => void | Promise<void>;
    };
    if (typeof loaded.default !== "function") {
      throw new Error(`${name}/index.ts provides no default export, so it is not a Pi extension entry`);
    }
    await loaded.default(pi);
  }
  await seedSecondParticipant(pi);
  if (process.env.PI_E2E_HOST === "team") {
    // Imported here, not at module scope: loading this module configures the tasks
    // store, and a combination without a team runtime must be left without it.
    // The bundle publishes the *real* team spawn path, because that is what makes
    // peer messaging work at all: the message tool resolves recipients from the
    // persisted roster, which only a team spawn writes. A fake host would register
    // an in-memory resident the message tool cannot see, and the suite would pass
    // a refusal off as delivery.
    const { registerSessionAgent } = await import("@fradser/pi-subagents");
    // The package's session_start publishes the shipping coordinator and clears
    // old session roles. Seed only the temporary role after that hook: a file on
    // disk now means saved-role persistence and selects the standalone path.
    // Neither install combination replaces native spawn/readiness with a host
    // that merely registers a roster entry and claims it started successfully.
    pi.on("session_start", () => {
      registerSessionAgent({
        name: "scout", tools: [],
        description: "Reads what it is pointed at and reports back",
        prompt: "Read the evidence you are given and report what it shows.",
      });
    });
  }
  installScriptedProvider(pi, {
    provider: "e2e-scripted",
    probe: PROBE,
    turns: SCENARIOS[SCENARIO] ?? SURFACE,
  });
}
