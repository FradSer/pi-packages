import {learningOutputSchema, type MemoryCitationDomain} from "./planner-output-schema";
import { plannerJsonOutputEnabled, plannerStructuredOutputEnabled } from "./config";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Loaded only by isolated learning workers, never by the parent task session. */
export default function plannerJsonOutput(pi: ExtensionAPI): void {
  pi.registerFlag("learning-output-schema", {type: "string", description: "Parent-selected learning worker output contract"});
  pi.registerFlag("learning-citation-domain", {type: "string", description: "Complete parent-owned eligible frozen citation positions"});
  pi.registerFlag("learning-candidate-ids", {type: "string", description: "Complete parent-owned eligible Memory amendment identities"});
  pi.registerFlag("learning-withdrawal-candidate-ids", {type: "string", description: "Parent-reviewed optional never-written new Memory drafts"});
  pi.registerFlag("learning-body-count", {type: "string", description: "Complete parent-owned independent Memory review group size"});
  pi.on("before_provider_request", (event, ctx) => {
    // Enable only the documented model/API combination. OpenAI compatibility
    // alone does not establish JSON-mode support for an arbitrary provider.
    // A gateway must be explicitly verified and opted in by the operator.
    // https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output
    if (ctx.model?.api !== "openai-completions"
      || !/(?:^|\/)qwen3\.8-flash(?:-\d{4}-\d{2}-\d{2})?$/.test(ctx.model.id)
      || pi.getActiveTools().length !== 0) return;
    const payload = event.payload;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return;
    const request = payload as Record<string, unknown>;
    if (!Array.isArray(request.messages) || request.response_format !== undefined) return;
    // The worker prompt already requires JSON. Constrain syntax at the service;
    // the parent still validates the unique plan, citations and mutation intent.
    const outputKind = pi.getFlag("learning-output-schema");
    let domain: MemoryCitationDomain | undefined;
    if (plannerStructuredOutputEnabled() && (outputKind === "memory-delta" || outputKind === "memory-retained-amendment" || outputKind === "memory-amendment" || outputKind === "memory-semantic-amendment" || outputKind === "memory-combined-amendment")) {
      const encoded = pi.getFlag("learning-citation-domain");
      if (encoded !== undefined) {
        if (encoded === "complete-catalog-overflow") throw new Error("Complete Memory citation domain exceeds worker argument bound");
        if (typeof encoded !== "string" || Buffer.byteLength(encoded) > 64_000) throw new Error("Invalid Memory citation domain");
        const parsed = JSON.parse(encoded);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)
          || Object.keys(parsed).some(key => !["indices", "refs"].includes(key))
          || !Array.isArray(parsed.indices) || !Array.isArray(parsed.refs)
          || parsed.indices.some((index: unknown) => !Number.isSafeInteger(index) || Number(index) < 0)
          || new Set(parsed.indices).size !== parsed.indices.length
          || new Set(parsed.refs).size !== parsed.refs.length
          || parsed.refs.some((ref: unknown) => typeof ref !== "string" || ref.length > 128
            || !/^e(0|[1-9]\d*)\.b(0|[1-9]\d*)\.[lp][1-9]\d*(?:\.c(?:0|[1-9]\d*)-[1-9]\d*)?$/.test(ref)
            || !parsed.indices.includes(Number(/^e(\d+)/.exec(ref)?.[1])))
          || parsed.indices.some((index: number) => !parsed.refs.some((ref: string) => ref.startsWith(`e${index}.`)))) throw new Error("Invalid Memory citation domain");
        domain = parsed;
      }
    }
    let candidateIds: string[] | undefined;
    if (plannerStructuredOutputEnabled() && (outputKind === "memory-amendment" || outputKind === "memory-semantic-amendment" || outputKind === "memory-combined-amendment")) {
      const encoded = pi.getFlag("learning-candidate-ids");
      if (encoded !== undefined) {
        if (typeof encoded !== "string" || Buffer.byteLength(encoded) > 64_000 || encoded === "complete-candidates-overflow") throw new Error("Invalid complete Memory candidate domain");
        const parsed: unknown = JSON.parse(encoded);
        if (!Array.isArray(parsed) || new Set(parsed).size !== parsed.length
          || parsed.some(id => typeof id !== "string" || !/^(?:operations|newMemories):(0|[1-9]\d*):[a-f0-9]{64}$/.test(id))) throw new Error("Invalid complete Memory candidate domain");
        candidateIds = parsed;
      }
    }
    let withdrawalCandidateIds: string[] | undefined;
    const encodedWithdrawals = pi.getFlag("learning-withdrawal-candidate-ids");
    if (plannerStructuredOutputEnabled() && encodedWithdrawals !== undefined) {
      if ((outputKind !== "memory-semantic-amendment" && outputKind !== "memory-combined-amendment")
        || typeof encodedWithdrawals !== "string" || Buffer.byteLength(encodedWithdrawals) > 64_000) throw new Error("Invalid parent Memory withdrawal domain");
      const parsed: unknown = JSON.parse(encodedWithdrawals);
      if (!Array.isArray(parsed) || !parsed.length || parsed.length > 32 || new Set(parsed).size !== parsed.length
        || parsed.some(id => typeof id !== "string" || !/^newMemories:(0|[1-9]\d*):[a-f0-9]{64}$/.test(id)
          || !candidateIds?.includes(id))) throw new Error("Invalid parent Memory withdrawal domain");
      withdrawalCandidateIds = parsed;
    }
    let bodyCount: number | undefined;
    if (plannerStructuredOutputEnabled() && outputKind === "memory-body-review") {
      const encoded = pi.getFlag("learning-body-count");
      if (typeof encoded !== "string" || !/^(?:[1-9]|[12]\d|3[0-2])$/.test(encoded)) throw new Error("Invalid complete Memory body count");
      bodyCount = Number(encoded);
    }
    const schema = plannerStructuredOutputEnabled() ? learningOutputSchema(outputKind, domain, candidateIds, bodyCount, withdrawalCandidateIds) : undefined;
    if (schema) return {...request, response_format: {type: "json_schema", json_schema: {
      name: String(outputKind).replaceAll("-", "_"), strict: true, schema,
    }}};
    if (plannerJsonOutputEnabled()) return { ...request, response_format: { type: "json_object" } };
  });
}
