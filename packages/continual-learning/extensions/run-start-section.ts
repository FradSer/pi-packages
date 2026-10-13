import type { BeforeAgentStartEvent } from "@earendil-works/pi-coding-agent";

/** Pi 1.2 sections preserve contributions when another owner sets customPrompt.
 * Reject unsupported runtimes rather than silently losing required guidance.
 */
export function setRunStartSection(
  options: BeforeAgentStartEvent["systemPromptOptions"],
  name: string,
  content: string,
): void {
  if ("sections" in options && options.sections && typeof options.sections === "object"
    && !Array.isArray(options.sections)) {
    if (content) Object.assign(options.sections, { [name]: content });
    else Reflect.deleteProperty(options.sections, name);
    return;
  }
  throw new Error("Continual-learning requires Pi 1.2 structured prompt sections.");
}
