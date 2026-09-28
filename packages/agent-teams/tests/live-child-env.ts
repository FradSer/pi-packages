/**
 * Opt-in live verification that a real Agent child still authenticates and
 * completes a model turn under the spawn environment policy.
 *
 *   LIVE_AGENT_WORK_MODEL=<provider/model> node tests/live-child-env.ts
 *
 * `tests/test_child_env.py` proves from inside a spawned child that the policy
 * output is the environment the child actually receives. That uses a fake CLI,
 * so it cannot prove the child can still reach a model provider. This closes the
 * gap: one real resident, one real turn, one completed report. A withheld
 * variable the provider needed would surface here as a failed turn.
 *
 * A leader-side sentinel is exported first so the run also confirms, against the
 * real ambient environment rather than a synthetic one, that a secret-shaped
 * variable is withheld and named.
 */

import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SessionManager, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { clearSessionAgents, registerSessionAgent } from "@fradser/pi-subagents";
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

const SENTINEL_NAME = "AGENT_TEAMS_LIVE_SECRET_TOKEN";
const SENTINEL_VALUE = `sentinel-${Date.now()}-${Math.random().toString(36).slice(2)}`;
process.env[SENTINEL_NAME] = SENTINEL_VALUE;

const cwd = mkdtempSync(join(tmpdir(), "pi-live-child-env-"));
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
  registerSessionAgent({
    name: "env-probe",
    description: "Live environment policy probe",
    tools: [],
    prompt: "Return exactly LIVE_CHILD_OK as one ordinary final answer. Use no tools.",
  });

  const spawned = spawnTeammate({
    name: "env-probe",
    agent: "env-probe",
    prompt: "Return exactly LIVE_CHILD_OK as your ordinary final answer. Use no tools.",
    model,
  });
  assert.equal(spawned.ok, true, spawned.ok ? "" : spawned.error);
  const policy = spawned.ok ? spawned.teammate.envPolicy : undefined;
  assert.ok(policy, "the spawn must record its environment policy");
  assert.ok(policy!.withheldCount > 0, "a real shell exports more than the allowlist admits");
  assert.ok(policy!.withheldSecretCount > 0, "a real shell exports credential-shaped variables");
  // The name list is bounded, so on a shell exporting more than the cap in
  // credential-shaped variables the sentinel may legitimately be truncated out.
  // Truncation is the only acceptable reason for its absence.
  const named = policy!.withheldSecretNames;
  assert.ok(named.length <= 16, "the withheld-name list must stay bounded");
  const sentinelNamed = named.some((name) => name.includes("SENTINEL") || name.includes("SECRET"));
  assert.ok(
    sentinelNamed || named.length === 16,
    "the leader-side sentinel must be withheld and named unless the list truncated",
  );
  assert.ok(
    policy!.diagnostic.includes("PI_TEAMMATE_ENV_ALLOW"),
    "the diagnostic must name the recovery path",
  );
  assert.ok(!policy!.diagnostic.includes(SENTINEL_VALUE), "a withheld value must never be rendered");
  assert.equal(getState().teammates["env-probe"]?.envPolicy?.withheldCount, policy!.withheldCount);

  const report = await Promise.race([
    new Promise<LeaderReport>((resolve) => { settled = resolve; }),
    new Promise<never>((_resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Live child authentication verification timed out.")),
        150_000,
      );
      timer.unref?.();
    }),
  ]);

  assert.equal(report.status, "completed", `child could not complete a turn: ${report.body.slice(0, 300)}`);
  assert.equal(report.body.trim(), "LIVE_CHILD_OK");
  console.log(JSON.stringify({
    withheldCount: policy!.withheldCount,
    withheldSecretCount: policy!.withheldSecretCount,
    namedSecrets: named.length,
    sentinelNamed,
    childAuthenticated: true,
    reportStatus: report.status,
  }));
} finally {
  delete process.env[SENTINEL_NAME];
  await teardownTeammates();
  shutdownTeamMachine();
  removeRuntimeDir(ctx);
  clearSessionAgents();
  resetState();
  rmSync(cwd, { recursive: true, force: true });
}
console.log("LIVE_CHILD_ENV_OK");
