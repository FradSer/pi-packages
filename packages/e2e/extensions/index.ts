/**
 * pi-e2e — judge a Gherkin `.feature` scenario against one run evidence file.
 *
 * Provides:
 *   1. Prompt injection (`context_with_system`): stable system capability note
 *      teaching the model when to verify scenarios and how to use e2e.
 *   2. Native tool `e2e_verify`: allows the agent to autonomously verify acceptance
 *      scenarios during development and testing loops.
 *   3. Harness gate (`agent_before_settle`): starts acceptance verification when
 *      a .feature file changes, and follows up on failed or missing verification.
 *   4. Interactive command `/e2e`: for human-initiated evaluations.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { E2E_FEEDBACK_MESSAGE_TYPE, type E2EFeedback } from "../src/feedback.ts";
import { E2EGate, registerE2EHarness } from "../src/harness.ts";
import { executeE2EVerify, registerE2ETools } from "../src/tool.ts";

const USAGE = "/e2e [verify] <feature.feature> <evidence.json> [scenario name]";

/** Registers tools, harness enforcement hooks, prompt injection, and slash commands. */
export default function e2eExtension(pi: ExtensionAPI): void {
  const gate = new E2EGate();

  // 1. Prompt injection and harness enforcement hooks
  registerE2EHarness(pi, gate);

  // 2. Native LLM tool for autonomous workflow integration
  registerE2ETools(pi, undefined, () => gate.verificationObserver());

  // 3. User-facing slash command
  pi.registerCommand("e2e", {
    description: `Judge a Gherkin scenario against run evidence. Usage: ${USAGE}`,
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/).filter((part) => part !== "");
      const tokens = parts[0]?.toLowerCase() === "verify" ? parts.slice(1) : parts;
      const [featureArg, evidenceArg, ...rest] = tokens;
      const send = (feedback: E2EFeedback, content = feedback.lines.join("\n")) => pi.sendMessage({
        customType:E2E_FEEDBACK_MESSAGE_TYPE,content,display:true,details:feedback,
      },{triggerTurn:false});
      if (featureArg === undefined || evidenceArg === undefined) {
        send({label:"needs review",tone:"warning",lines:[`Usage: ${USAGE}`]});
        return;
      }
      send({label:"running",tone:"warning",lines:["Evaluating caller-supplied evidence"]});
      const observer = gate.verificationObserver();
      const result = await executeE2EVerify({feature:featureArg,evidence:evidenceArg,
        ...(rest.length > 0 ? {scenario:rest.join(" ")} : {})},observer.onVerdict,
        {cwd:ctx.cwd,signal:ctx.signal,onError:observer.onError});
      if (result.details?.feedback) send(result.details.feedback,result.content.map(item=>item.text).join("\n"));
    },
  });
}
