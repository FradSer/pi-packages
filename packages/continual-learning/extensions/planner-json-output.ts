import { plannerJsonOutputEnabled } from "./config";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Loaded only by isolated learning workers, never by the parent task session. */
export default function plannerJsonOutput(pi: ExtensionAPI): void {
  pi.on("before_provider_request", (event, ctx) => {
    // Enable only the documented model/API combination. OpenAI compatibility
    // alone does not establish JSON-mode support for an arbitrary provider.
    // A gateway must be explicitly verified and opted in by the operator.
    // https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output
    if (!plannerJsonOutputEnabled() || ctx.model?.api !== "openai-completions"
      || !/(?:^|\/)qwen3\.8-flash(?:-\d{4}-\d{2}-\d{2})?$/.test(ctx.model.id)
      || pi.getActiveTools().length !== 0) return;
    const payload = event.payload;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return;
    const request = payload as Record<string, unknown>;
    if (!Array.isArray(request.messages) || request.response_format !== undefined) return;
    // The worker prompt already requires JSON. Constrain syntax at the service;
    // the parent still validates the unique plan, citations and mutation intent.
    return { ...request, response_format: { type: "json_object" } };
  });
}
