import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { previewHarnessRuleCases } from "./harness-consolidation";

/** The child can evaluate its own cases; only the parent can approve a plan. */
export function registerHarnessPlannerPreview(pi: ExtensionAPI): void {
  let calls = 0;
  pi.registerTool({
    name: "harness_check_cases", label: "Check proposed Harness cases",
    description: "Read-only evaluation of a proposed rule and cases:{positive:[],negative:[]}, using the actual parent rule evaluator. No commands run. Check and correct mismatches before final JSON. Passing cases do not approve evidence, scope, semantics, ownership or writing. At most eight calls.",
    // Unknown fields expose no JSON type to providers, which can solicit JSON
    // strings instead of objects and spend the entire repair budget on shape errors.
    // Describe transport shape here; the parent evaluator still validates meaning.
    parameters: Type.Object({
      rule: Type.Object({
        id: Type.String(),
        enabled: Type.Optional(Type.Boolean()),
        bash: Type.Optional(Type.String()),
        skill: Type.Optional(Type.String()),
        text: Type.Optional(Type.String()),
        action: Type.Optional(Type.Union([Type.Literal("confirm"), Type.Literal("block")])),
        message: Type.Optional(Type.String()),
        instructions: Type.Optional(Type.String()),
      }),
      cases: Type.Object({
        positive: Type.Array(Type.Object({
          bash: Type.Optional(Type.String()), skill: Type.Optional(Type.String()),
          text: Type.Optional(Type.Array(Type.String())),
          expected: Type.Optional(Type.Union([Type.Literal("match"), Type.Literal("execute"), Type.Literal("confirm"), Type.Literal("block")])),
        })),
        negative: Type.Array(Type.Object({
          bash: Type.Optional(Type.String()), skill: Type.Optional(Type.String()),
          text: Type.Optional(Type.Array(Type.String())),
          expected: Type.Optional(Type.Literal("no-match")),
        })),
      }),
    }),
    async execute(_id, params, signal) {
      signal?.throwIfAborted();
      calls += 1;
      if (calls >= 8) pi.setActiveTools(pi.getActiveTools().filter(name => name !== "harness_check_cases"));
      const result = calls > 8 ? {passed:false, errors:["Harness case preview budget exceeded"]}
        : Buffer.byteLength(JSON.stringify(params)) > 220_000 ? {passed:false, errors:["Harness case preview input exceeds bound"]}
        : previewHarnessRuleCases(params.rule, params.cases);
      const details = {...result, authorizesMutation:false};
      return {content:[{type:"text" as const, text:JSON.stringify(details)}], details, isError:!result.passed};
    },
  });
  pi.on("session_start", async () => { pi.setActiveTools(["learning_read", "harness_check_cases"]); });
}

export async function harnessPlannerPreviewArgs(directory: string): Promise<string[]> {
  const extension = path.join(directory, `harness-preview-${randomUUID()}.mjs`);
  await fs.writeFile(extension, `import {registerHarnessPlannerPreview} from ${JSON.stringify(fileURLToPath(import.meta.url))};\nexport default pi => registerHarnessPlannerPreview(pi);\n`, {mode:0o600, flag:"wx"});
  return ["-e", extension];
}
