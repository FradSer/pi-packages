/** Drive the real extension entry and tool; only OS spawn/close is replaced. */
import assert from "node:assert/strict";
import { mock } from "node:test";
import * as spawner from "../src/spawner.ts";

const mode = process.argv[2];
let completeShutdown: () => Promise<Array<{ name: string; confirmedClosed: boolean }>> = async () => [];
mock.module(new URL("../src/spawner.ts", import.meta.url).href, {
  namedExports: { ...spawner,
    spawnResident: () => ({ pid: 7, readiness: Promise.resolve(true) }),
    deliverResidentPrompt: async () => true,
    terminateAgent: async () => ({ outcome: "closed" }),
    terminateAllAgents: () => completeShutdown(),
  },
});
const { default: extension, executeChildIntent, getAgent, updateAgent, resetRoster, clearSessionAgents }
  = await import("../index.ts");
resetRoster(); clearSessionAgents();
const hooks = new Map<string, () => Promise<void>>();
const pi = { registerTool() {}, registerMessageRenderer() {}, events: { emit() {} },
  on(name: string, handler: () => Promise<void>) { hooks.set(name, handler); } };
extension(pi as never);
const call = (params: Record<string, unknown>) => executeChildIntent(params, { cwd: process.cwd() });
const first = await call({ name: "retire-check" });
assert.equal(first.details.ok, true, JSON.stringify(first));
const firstSession = String(first.details.session);
const residents = (globalThis as Record<symbol, Map<string, unknown>>)[Symbol.for("fradser.pi-subagents.resident-bindings")];
const hosts = (globalThis as Record<symbol, Map<string, unknown>>)[Symbol.for("fradser.pi-subagents.host-bindings")];
assert.ok(residents.has(firstSession));
hosts.set(firstSession, { retiredRuntime: true });
let successor: string | undefined;
if (mode === "already-stopped") updateAgent("retire-check", { status: "stopped", leaderRequestedEnd: true });
completeShutdown = async () => {
  if (mode === "replacement") {
    updateAgent("retire-check", { status: "stopped", leaderRequestedEnd: true });
    const next = await call({ name: "retire-check" });
    assert.equal(next.details.ok, true, JSON.stringify(next));
    successor = String(next.details.session);
    hosts.set(successor, { currentRuntime: true });
  }
  return mode === "already-stopped" ? [] : [{ name: "retire-check", confirmedClosed: mode !== "unconfirmed" }];
};
await hooks.get("session_shutdown")!();
const expectedRetired = mode !== "unconfirmed";
assert.equal(residents.has(firstSession), !expectedRetired, "Old resident closure retirement follows confirmed shutdown");
assert.equal(hosts.has(firstSession), !expectedRetired, "Old host closure retirement follows confirmed shutdown");
if (successor) {
  assert.ok(residents.has(successor) && hosts.has(successor), "Exact-handle retirement preserves successor closures");
  assert.equal(getAgent("retire-check")?.status, "idle");
  const accepted = await call({ operation: "input", delivery: "next", session: successor, prompt: "Continue" });
  assert.equal(accepted.details.ok, true, JSON.stringify(accepted));
} else if (mode === "unconfirmed") {
  assert.equal(getAgent("retire-check")?.status, "idle");
  assert.equal(getAgent("retire-check")?.leaderRequestedEnd, true);
} else assert.equal(getAgent("retire-check")?.status, "stopped");
console.log(JSON.stringify({ ok: true, mode }));
