/**
 * pi-continual-learning — the harness surface of continual learning.
 *
 * Intelligence is not only in model weights; it accumulates across the
 * system's components. This package owns two of the three surfaces:
 *
 * - Harness: flat skill, Bash and retained-text rules, including the guidance
 *   those rules deliver, with explicit Bash gates.
 * - Context: memory retrieval and learning from settled user tasks through
 *   parent-validated plans.
 *
 * Model weights are explicitly out of scope.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import injectMemory from "./extensions/inject-memory.ts";
import registerGuardrails from "./extensions/guardrails.ts";
import registerHarnessGuidance from "./extensions/harness-guidance.ts";
import registerOutputChecks from "./extensions/output-checks.ts";

export default function (pi: ExtensionAPI) {
  injectMemory(pi);
  registerHarnessGuidance(pi);
  registerGuardrails(pi);
  registerOutputChecks(pi);
}
