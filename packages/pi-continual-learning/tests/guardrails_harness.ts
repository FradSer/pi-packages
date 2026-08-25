/** Runtime harness for the guardrail engine, driven by pytest via tsx.
 * Each invocation prints one JSON line describing the decision. */

import { evaluate, mergeLayers } from "./guardrail-engine.ts";
import type { PolicyLayer } from "./guardrail-types.ts";

interface Invocation {
  op: "merge+evaluate" | "merge";
  layers: PolicyLayer[];
  call?: { toolName: string; args: Record<string, unknown> };
}

const payload = JSON.parse(process.argv[2] ?? "{}") as Invocation;

if (payload.op === "merge") {
  const result = mergeLayers(payload.layers);
  console.log(
    JSON.stringify({
      names: result.policies.map((p) => p.name),
      errors: result.errors,
    }),
  );
} else {
  const config = mergeLayers(payload.layers);
  const decision = evaluate(config, {
    toolName: payload.call?.toolName ?? "bash",
    args: payload.call?.args ?? {},
  });
  console.log(JSON.stringify(decision ? { matched: true, ...decision } : { matched: false }, null, 0));
}
