/**
 * pi-continual-learning — the harness surface of continual learning.
 *
 * Intelligence is not only in model weights; it accumulates across the
 * system's components. This package owns two of the three surfaces:
 *
 * - Harness: dynamically updated tool-call logic via declarative guardrail
 *   policies (extensions/guardrails.ts), evaluated on every tool call with
 *   corrective guidance fed back to the model.
 * - Prompts: memory retrieval and injection (extensions/inject-memory.ts),
 *   keeping task-intent mapping and system guidance current across sessions.
 *
 * Model weights are explicitly out of scope.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import injectMemory from "./extensions/inject-memory.ts";
import registerGuardrails from "./extensions/guardrails.ts";

export default function (pi: ExtensionAPI) {
  injectMemory(pi);
  registerGuardrails(pi);
}
