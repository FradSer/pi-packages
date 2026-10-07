/**
 * pi-e2e — judge a Gherkin `.feature` scenario against one run evidence file.
 *
 * Provides:
 *   1. Prompt injection (`context_with_system`): stable system capability note
 *      teaching the model when to verify scenarios and how to use e2e.
 *   2. Native tool `e2e_verify`: allows the agent to autonomously verify acceptance
 *      scenarios during development and testing loops.
 *   3. Harness gate (`agent_before_settle`): intervenes before turn settlement
 *      if a scenario verification failed or if requested verification was omitted.
 *   4. Interactive command `/e2e`: for human-initiated evaluations.
 */

import path from "node:path";
import process from "node:process";
import { readFile } from "node:fs/promises";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import { firstScenario, parseFeature, scenarioByName } from "../src/gherkin.ts";
import { E2EGate, registerE2EHarness } from "../src/harness.ts";
import { registerE2ETools } from "../src/tool.ts";
import type { Evidence } from "../src/types.ts";
import { verifyScenario } from "../src/verify.ts";

const USAGE = "/e2e [verify] <feature.feature> <evidence.json> [scenario name]";

async function readText(target: string): Promise<string> {
  return readFile(path.resolve(process.cwd(), target), "utf-8");
}

/** Registers tools, harness enforcement hooks, prompt injection, and slash commands. */
export default function e2eExtension(pi: ExtensionAPI): void {
  const gate = new E2EGate();

  // 1. Prompt injection and harness enforcement hooks
  registerE2EHarness(pi, gate);

  // 2. Native LLM tool for autonomous workflow integration
  registerE2ETools(pi, (verdict) => gate.recordVerdict(verdict));

  // 3. User-facing slash command
  pi.registerCommand("e2e", {
    description: `Judge a Gherkin scenario against run evidence. Usage: ${USAGE}`,
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/).filter((part) => part !== "");
      const tokens = parts[0]?.toLowerCase() === "verify" ? parts.slice(1) : parts;
      const [featureArg, evidenceArg, ...rest] = tokens;
      if (featureArg === undefined || evidenceArg === undefined) {
        notifyPi(ctx.ui, `Usage: ${USAGE}`, "warning");
        return;
      }
      try {
        const file = parseFeature(await readText(featureArg));
        const wanted = rest.join(" ");
        const scenario =
          wanted === "" ? firstScenario(file) : scenarioByName(file, wanted);
        if (scenario === undefined) {
          notifyPi(ctx.ui, `Scenario "${wanted}" is not in ${featureArg}.`, "error");
          return;
        }
        const evidence = JSON.parse(await readText(evidenceArg)) as Evidence;
        const result = await verifyScenario({ scenario, evidence });
        const { verdict } = result;
        gate.recordVerdict(verdict);

        const line = `${verdict.status} · ${verdict.clauses.filter((clause) => clause.status === "met").length}/${verdict.clauses.length} clauses met · ${verdict.reason}`;
        notifyPi(ctx.ui, line, verdict.status === "fulfilled" ? "info" : "warning");
        if (result.modelError !== undefined) notifyPi(ctx.ui, result.modelError, "warning");
      } catch (error) {
        notifyPi(ctx.ui, `e2e verify failed: ${(error as Error).message}`, "error");
      }
    },
  });
}
