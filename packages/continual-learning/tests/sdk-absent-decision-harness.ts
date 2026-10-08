/**
 * The decision an enabled judge makes when the SDK is absent.
 *
 * Jev is optional: a judge that cannot run must not change the Memory outcome, so
 * the parent's own validated plan proceeds as with Jev off, and the reason stays in
 * telemetry. A Harness constraint keeps the conservative hold, so unavailability
 * never releases a constraint.
 */
import { mock } from "bun:test";

mock.module("@typesafe-ai/sdk", () => {
  throw new Error("Cannot find module '@typesafe-ai/sdk'");
});

const { createJevJudge } = await import("../extensions/jev-learning.ts");

const evidence = { contextEnabled: true, entries: [{ role: "user", content: "Remember that I prefer concise updates." }] };
const candidate = {
  name: "concise.md", kind: "preference", classification: "private",
  content: "---\nname: concise\ndescription: Prefer concise updates\ntype: feedback\n---\nPrefer concise updates.\n",
  evidence: [{ index: 0, quote: "Remember that I prefer concise updates.", role: "user" }],
};
const judge = createJevJudge({ enabled: true, apiKey: "fixture-absent-sdk", defaultModel: "jev-1.13.0",
  scopes: ["memory", "harness"], allowPrivateMemory: true });
const memory = await judge.validate("memory", evidence, [candidate], []);
const harness = await judge.validate("harness", evidence, [candidate], []);
console.log(JSON.stringify({
  memory: { decision: memory.decision, reason: memory.telemetry.reason },
  harness: { decision: harness.decision, reason: harness.telemetry.reason },
}));
