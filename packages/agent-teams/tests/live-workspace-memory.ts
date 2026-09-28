/**
 * Opt-in live verification of the durable workspace and Agent Memory path.
 *
 *   LIVE_AGENT_WORK_MODEL=<provider/model> node tests/live-workspace-memory.ts
 *
 * `tests/test_agent_workspace.py` exercises `ensureAgentWorkspace` directly and
 * `tests/live-child-env.ts` spawns in a non-repository temporary directory, which
 * takes the shared-workspace fallback. Neither proves the new default path end to
 * end: a real repository, a real child process, a workspace created and then
 * PRESERVED rather than removed, and a Pi session persisted under that workspace's
 * working path.
 *
 * Everything is redirected to a temporary agent directory, so a real Agent's
 * workspace and memory are never touched.
 */

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { SessionManager, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { clearSessionAgents, discoverAgents } from "@fradser/pi-subagents";
import { getState, resetState } from "../src/state.ts";
import {
  initTeamMachine,
  removeRuntimeDir,
  shutdownTeamMachine,
  spawnTeammate,
  teardownTeammates,
} from "../src/team-machine.ts";
import type { LeaderReport } from "@fradser/pi-subagents";

const model = process.env.LIVE_AGENT_WORK_MODEL;
assert.ok(model, "LIVE_AGENT_WORK_MODEL must select an authenticated model for this opt-in test.");

const root = mkdtempSync(join(tmpdir(), "pi-live-workspace-"));
const agentDir = join(root, "agent-dir");
const project = join(root, "project");
mkdirSync(agentDir, { recursive: true });
mkdirSync(project, { recursive: true });
// Redirecting the agent directory isolates the workspaces, sessions, and memory
// this test creates — but it also hides the real credentials, so the child could
// not authenticate. Link the auth-bearing files through instead of copying them:
// a test must never duplicate a secret onto disk.
const realAgentDir = process.env.PI_CODING_AGENT_DIR ?? join(homedir(), ".pi", "agent");
for (const name of ["auth.json", "models.json", "settings.json"]) {
  const target = join(realAgentDir, name);
  if (existsSync(target)) symlinkSync(target, join(agentDir, name));
}
process.env.PI_CODING_AGENT_DIR = agentDir;

function git(...args: string[]): string {
  return execFileSync("git", ["-C", project, ...args], { encoding: "utf-8" }).trim();
}
git("init", "-q");
git("config", "user.email", "agent@example.test");
git("config", "user.name", "agent");
writeFileSync(join(project, "tracked.txt"), "base\n");
git("add", "-A");
git("commit", "-qm", "base");

// A persisted definition that opts into Agent Memory, so this is not a Temporary
// Agent and the memory folder is legitimate.
const agentsDir = join(agentDir, "agents");
mkdirSync(agentsDir, { recursive: true });
writeFileSync(
  join(agentsDir, "memory-probe.md"),
  [
    "---",
    "name: memory-probe",
    "description: Live workspace and memory probe",
    "tools: read, write",
    "memory: true",
    "---",
    "Return exactly LIVE_WS_OK as one ordinary final answer. Use no tools.",
    "",
  ].join("\n"),
);
// One pre-existing memory entry, so the injected index has something to list.
const memoryRoot = join(agentsDir, "memory-probe");
mkdirSync(memoryRoot, { recursive: true });
writeFileSync(
  join(memoryRoot, "existing-method.md"),
  "---\nname: existing-method\ndescription: Use when probing live behaviour.\ntype: capability\n---\n\nAn existing capability record.\n",
);

const cwd = project;
const sessionManager = SessionManager.inMemory(cwd);
const ctx = { cwd, sessionManager, mode: "print", hasUI: false } as ExtensionContext;
let settled: ((report: LeaderReport) => void) | undefined;

try {
  resetState();
  initTeamMachine(ctx, {
    notifyChange() {},
    sendUpdate(report) {
      if (!report.finished) return;
      settled?.(report);
    },
  });
  const discovered = discoverAgents(cwd).get("memory-probe");
  assert.ok(discovered, "the persisted definition must be discovered");
  assert.equal(discovered!.memory, true, "memory must be opted in by the definition");
  assert.equal(discovered!.isolation, "isolated", "isolation is the default");

  const spawned = spawnTeammate({
    name: "memory-probe",
    agent: "memory-probe",
    prompt: "Return exactly LIVE_WS_OK as your ordinary final answer. Use no tools.",
    model,
  });
  assert.equal(spawned.ok, true, spawned.ok ? "" : spawned.error);
  const teammate = spawned.ok ? spawned.teammate : undefined;
  const workspaceCwd = teammate?.cwd;
  assert.ok(workspaceCwd && workspaceCwd !== project, "the child must run in its own workspace");
  assert.equal(teammate?.isolation, "worktree");
  assert.ok(
    workspaceCwd!.startsWith(join(agentDir, "workspaces", "memory-probe")),
    `workspace must be durable and user-scoped, got ${workspaceCwd}`,
  );

  const report = await Promise.race([
    new Promise<LeaderReport>((resolve) => { settled = resolve; }),
    new Promise<never>((_resolve, reject) => {
      // Deliberately not unref'd: a child that never reports must surface as a
      // timeout rather than letting the process exit silently on an empty loop.
      setTimeout(() => reject(new Error("Live workspace verification timed out; the child never reported.")), 150_000);
    }),
  ]);
  assert.equal(report.status, "completed", `child could not complete: ${report.body.slice(0, 300)}`);
  assert.equal(report.body.trim(), "LIVE_WS_OK");

  // The decisive assertions: durability. Completion must not remove the workspace,
  // and Pi must have stored a session under that working path — that pairing is
  // what makes the workspace the Agent's working memory.
  assert.ok(existsSync(workspaceCwd!), "completion must not remove a durable workspace");
  const sessionGroups = join(agentDir, "sessions");
  const groups = existsSync(sessionGroups) ? readdirSync(sessionGroups) : [];
  assert.ok(groups.length > 0, "Pi must have persisted a session for the child");
  const escaped = workspaceCwd!.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-");
  assert.ok(
    groups.some((group) => group.includes(escaped) || group.includes("memory-probe")),
    `no session group for the workspace path; groups were ${groups.join(", ")}`,
  );

  // A second attempt must resolve the same workspace, which is what preserves
  // working memory. Asserted through ensureAgentWorkspace rather than a second
  // spawn: a resident stays alive after its report, so re-spawning the same name
  // is refused by the roster rather than exercising reuse.
  const { ensureAgentWorkspace } = await import("@fradser/pi-subagents");
  const reuse = ensureAgentWorkspace({ agentName: "memory-probe", cwd: project, isolation: "isolated" });
  assert.equal(reuse.cwd, workspaceCwd, "the workspace path must be stable across attempts");
  assert.equal(reuse.reused, true, "a second attempt must reuse, not recreate");

  console.log(JSON.stringify({
    workspaceDurable: true,
    sessionPersisted: true,
    reusedOnSecondAttempt: reuse.reused,
    memoryOptedIn: true,
    reportStatus: report.status,
    recordedIsolation: getState().teammates["memory-probe"]?.isolation,
    recordedTools: getState().teammates["memory-probe"]?.tools,
    branch: git("branch", "--list", "agent/memory-probe") || "(none)",
  }));
} finally {
  await teardownTeammates();
  shutdownTeamMachine();
  removeRuntimeDir(ctx);
  clearSessionAgents();
  resetState();
  delete process.env.PI_CODING_AGENT_DIR;
  rmSync(root, { recursive: true, force: true });
}
console.log("LIVE_WORKSPACE_MEMORY_OK");
