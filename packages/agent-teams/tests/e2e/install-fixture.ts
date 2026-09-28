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

/**
 * Resolve `$prev.a.b` against the tool results so far, newest first.
 *
 * A script usually reads a list between creating a task and acting on it, so the
 * value being referenced is rarely in the immediately preceding result. Falling
 * back through the results means a script names the field it wants and the
 * harness finds the call that produced it, rather than every script having to
 * thread a value through a step it does not care about.
 */
function resolve(value: unknown, results: unknown[]): unknown {
  if (typeof value !== "string" || !value.startsWith("$prev")) return value;
  const path = value.slice("$prev".length).replace(/^\./, "");
  for (const details of [...results].reverse()) {
    let current: unknown = details;
    let found = true;
    for (const key of path.split(".").filter(Boolean)) {
      if (current === null || typeof current !== "object") { found = false; break; }
      current = (current as Record<string, unknown>)[key];
    }
    if (found && current !== undefined) return current;
  }
  return undefined;
}

const SURFACE: ScriptedTurn[] = [{ tool: PROBE, args: {} }];

/**
 * A child session's whole life, through the tool surface only.
 *
 * `start` with no prompt is the idle-resident shape: it enters the worker pool and
 * waits for work rather than burning a model turn. That is the case a team depends
 * on, so it is the one exercised here.
 */
const AGENT_LIFECYCLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "agent", args: { action: "start", name: "scout", tools: [] } },
  { tool: "agent", args: { action: "list" } },
  { tool: "agent", args: { action: "inspect", session: "$prev.session" } },
  { tool: "agent", args: { action: "stop", session: "$prev.session" } },
];

/** create → take → complete, all through one tool in one process. */
const BOARD_LIFECYCLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "task", args: { action: "create", subject: "Ship the release", resources: ["firmware"] } },
  { tool: "task", args: { action: "list", claimable: true } },
  { tool: "task", args: { action: "update", id: "$prev.id", status: "in_progress" } },
  { tool: "task", args: { action: "complete", id: "$prev.id", outcome: "success", result: "released" } },
  { tool: "task", args: { action: "list" } },
];

/**
 * A board with more than one participant, and a take refused for overlap.
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
const RESIDENT_TAKES: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  { tool: "agent", args: { action: "start", name: "scout", tools: [] } },
  { tool: "task", args: { action: "create", subject: "Rewrite the parser", resources: ["firmware"] } },
  { tool: "task", args: { action: "list", claimable: true } },
  { tool: "task", args: { action: "update", id: "$prev.id", status: "in_progress" } },
  { tool: "task", args: { action: "create", subject: "Rebuild the toolchain", resources: ["toolchain"] } },
  { tool: "task", args: { action: "update", id: "$prev.id", status: "in_progress" } },
  { tool: "task", args: { action: "list" } },
];

/**
 * All three tools, and a message that reaches a live peer.
 *
 * The recipient is a resident the scenario started, so the assertion is that a
 * request was routed to a real participant rather than that the tool existed. A
 * bogus recipient would only prove the tool refuses.
 */
const BUNDLE: ScriptedTurn[] = [
  { tool: PROBE, args: {} },
  // Started with a prompt, which is what gives the resident an open assignment. Mail
  // is work-bound: a message to a participant holding nothing is refused, and that
  // refusal is correct rather than a delivery failure.
  { tool: "agent", args: { action: "start", name: "scout", prompt: "Audit the parser changes" } },
  { tool: "task", args: { action: "create", subject: "Coordinate the release" } },
  { tool: "task", args: { action: "update", id: "$prev.id", status: "in_progress" } },
  { tool: "message", args: { to: "scout", body: "Take the parser first", kind: "request" } },
];

const SCENARIOS: Record<string, ScriptedTurn[]> = {
  surface: SURFACE,
  "agent-lifecycle": AGENT_LIFECYCLE,
  "board-lifecycle": BOARD_LIFECYCLE,
  "resident-takes": RESIDENT_TAKES,
  bundle: BUNDLE,
};

/**
 * Seed a second participant that already holds the toolchain.
 *
 * Only when the combination includes a board. The point is that the refusal a
 * suite asserts is produced by the real conflict check rather than staged: the peer
 * is on the roster, its holding is a real task, and the overlap is real.
 */
async function seedSecondParticipant(): Promise<void> {
  if (process.env.PI_E2E_HOST !== "peer") return;
  const { registerTeammate } = await import("@fradser/pi-subagents");
  const { createTask, takeTask } = await import("@fradser/pi-tasks");
  registerTeammate({
    name: "peer",
    agent: "peer",
    spawnId: "e2e-peer",
    pid: 0,
    status: "working",
    isolation: "none",
    currentTaskId: "peer-toolchain",
    assignment: { id: "board:peer", kind: "board", resources: ["toolchain"] },
    createdAt: 1,
    updatedAt: 1,
  });
  // A real task and a real take, so the holding the conflict check looks for is one
  // the board actually recorded. Seeding the roster entry alone would leave the two
  // disagreeing, and the check would walk a roster that knows nothing about it.
  createTask({ id: "peer-toolchain", subject: "Hold the toolchain", resources: ["toolchain"] });
  const taken = takeTask("peer-toolchain", "peer");
  if (!taken.ok) throw new Error(`could not seed the peer holding: ${taken.reason}`);
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
  await seedSecondParticipant();
  if (process.env.PI_E2E_HOST === "team") {
    // Imported here, not at module scope: loading this module configures the board
    // store, and a combination without a team runtime must be left without it.
    // The bundle publishes the *real* team spawn path, because that is what makes
    // peer messaging work at all: the message tool resolves recipients from the
    // persisted roster, which only a team spawn writes. A fake host would register
    // an in-memory resident the message tool cannot see, and the suite would pass
    // a refusal off as delivery.
    const team = await import("../../src/team-machine.ts");
    const subagents = await import("@fradser/pi-subagents");
    const { setAgentHost, exactSessionRoute } = subagents;
    // The role is written where `discoverAgents` reads it rather than registered in
    // memory. A module registry is only shared if both sides happened to resolve the
    // same instance, and a bare specifier reaching the same file through a symlinked
    // node_modules is exactly the kind of thing that decides differently by accident.
    // A definition file is the documented mechanism and has no identity to lose.
    // A team spawn refuses a name with no role in any scope, so the role has to
    // exist before the resident does. This is the same registration the standalone
    // path performs, which is why the two installs behave the same about a name.
    const fs = await import("node:fs");
    const path = await import("node:path");
    const dir = path.join(process.env.PI_CODING_AGENT_DIR ?? "", "agents");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "scout.md"), [
      "---",
      "description: Reads what it is pointed at and reports back",
      "tools: []",
      "---",
      "Read the evidence you are given and report what it shows.",
      "",
    ].join("\n"), "utf-8");
    setAgentHost({
      start(request) {
        const spawned = team.spawnTeammate({
          name: request.name,
          agent: request.name,
          ...(request.prompt ? { prompt: request.prompt } : {}),
          ...(request.model ? { model: request.model } : {}),
        });
        if (!spawned.ok) return spawned;
        const teammate = spawned.teammate;
        return { ok: true, session: exactSessionRoute(teammate.name, teammate.spawnId) };
      },
      stop: (name, spawnId) => team.shutdownTeammateExact(name, spawnId),
    });
  }
  if (process.env.PI_E2E_HOST === "peer") {
    const { setAgentHost, exactSessionRoute, registerTeammate, updateTeammate } =
      await import("@fradser/pi-subagents");
    setAgentHost({
      start(request) {
        const spawnId = `e2e-${request.name}`;
        const registered = registerTeammate({
          name: request.name,
          agent: request.name,
          spawnId,
          pid: 0,
          status: "idle",
          isolation: "none",
          createdAt: 1,
          updatedAt: 1,
        });
        if (!registered.ok) return { ok: false, error: registered.error };
        return { ok: true, session: exactSessionRoute(request.name, spawnId) };
      },
      stop: (name) => {
        updateTeammate(name, { status: "stopped" });
        return Promise.resolve({ ok: true });
      },
    });
  }
  installScriptedProvider(pi, {
    provider: "e2e-scripted",
    probe: PROBE,
    turns: SCENARIOS[SCENARIO] ?? SURFACE,
    resolve: (value: unknown, previous: unknown) => resolve(value, previous),
  });
}
