/** Skill-specific context guidance for the pre-generation surface.
 *
 * This hook is intentionally separate from guardrails: skill prompts shape
 * the model context, while guardrail policies enforce tool calls and
 * post-generation checks. A skill prompt applies only to the exact expanded
 * skill invocation parsed by Pi.
 */

import { parseSkillBlock, ToolExecutionComponent, type BeforeAgentStartEvent, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { createStaticToolLifecycleMessageRenderer, eventToolLifecycle, safeDisplayText } from "@fradser/pi-kit";
import { resolveHarnessConfig } from "./guardrail-config.ts";
import type { ResolvedConfig } from "./guardrail-types.ts";

export interface ContextGuidanceEvent {
  kind: "skill-prompt";
  skill: string;
  target: "system" | "user";
  prompt: string;
  source: string;
  file: string;
}

const injectedUserPromptContexts = new WeakSet<object>();

function appendSystemGuidance(systemPrompt: string, guidance: string): string {
  if (systemPrompt.includes(guidance)) return systemPrompt;
  return systemPrompt ? `${systemPrompt}\n\n${guidance}` : guidance;
}

function sourceFile(source: string | undefined, paths: ReturnType<typeof resolveHarnessConfig>["paths"]): string {
  switch (source) {
    case "user": return paths.user;
    case "project": return paths.project;
    case "project.local": return paths.projectLocal;
    default: return "(built-in)";
  }
}

export function skillPromptTarget(
  event: Pick<BeforeAgentStartEvent, "prompt">,
  config: ResolvedConfig,
): { name: string; prompt: string; target: "system" | "user"; source?: string } | undefined {
  const skill = parseSkillBlock(event.prompt);
  if (!skill) return undefined;
  const guidance = config.skillPrompts[skill.name];
  if (!guidance) return undefined;
  if (guidance.userMessagePattern && !new RegExp(guidance.userMessagePattern).test(skill.userMessage ?? "")) {
    return undefined;
  }
  return { name: skill.name, ...guidance };
}

/** Register configured skill guidance without registering any enforcement
 * hook. Root composition should call this beside registerGuardrails. */
export default function registerContextGuidance(pi: ExtensionAPI): void {
  pi.registerEntryRenderer("context-guidance-event", (entry, { expanded }, theme) => {
    const details = entry.data as ContextGuidanceEvent | undefined;
    const prompt = safeDisplayText(details?.prompt ?? "context guidance");
    const subject = safeDisplayText(details?.skill ?? "skill guidance");
    return createStaticToolLifecycleMessageRenderer({
      createSpec: () => eventToolLifecycle("context", subject, {
        label: "skill prompt",
        details: details ? [
          `skill=${details.skill}`,
          `target=${details.target}`,
          `source=${details.source}`,
          `file=${details.file}`,
          "",
          "prompt:",
          prompt,
        ] : undefined,
      }),
      expandHint: "ctrl+o to expand",
      fit: truncateToWidth,
      visibleWidth,
      wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
      hostComponent: ToolExecutionComponent,
    })({ content: "", details }, { expanded }, theme);
  });

  pi.on("before_agent_start", (event, ctx) => {
    const resolved = resolveHarnessConfig(ctx.cwd || process.cwd());
    const matched = skillPromptTarget(event, resolved.config);
    if (!matched) return undefined;
    if (matched.target === "user" && injectedUserPromptContexts.has(ctx)) return undefined;
    if (matched.target === "user") injectedUserPromptContexts.add(ctx);
    pi.appendEntry("context-guidance-event", {
      kind: "skill-prompt",
      skill: matched.name,
      target: matched.target,
      prompt: matched.prompt,
      source: matched.source ?? "unknown",
      file: sourceFile(matched.source, resolved.paths),
    } satisfies ContextGuidanceEvent);

    if (matched.target === "system") {
      return { systemPrompt: appendSystemGuidance(event.systemPrompt, matched.prompt) };
    }
    return {
      message: {
        customType: "skill-prompt-guidance",
        content: matched.prompt,
        display: false,
        details: { skill: matched.name, target: "user" },
      },
    };
  });
}
