/**
 * Skill-specific and text-specific context guidance for the pre-generation
 * surface.
 *
 * Delivery is a single persistent before_agent_start message per turn, so
 * guidance is retained on the branch, deduplicated against what is already
 * retained, and keeps the request prefix stable for caching. The ephemeral
 * `context` hook is intentionally NOT used: its return value builds one request
 * and is never persisted, which would re-append guidance every call and break
 * the prefix.
 *
 * Timing limitation (by design): before_agent_start fires once per user prompt,
 * so a keyword that first appears in a mid-run tool result is picked up on the
 * next agent start, not within the same run.
 */

import {
  buildSessionContext,
  parseSkillBlock,
  ToolExecutionComponent,
  type BeforeAgentStartEvent,
  type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { createStaticToolLifecycleMessageRenderer, eventToolLifecycle, safeDisplayText } from "@fradser/pi-kit";
import { resolveHarnessConfig } from "./guardrail-config.ts";
import { evaluateSkill } from "./guardrail-engine.ts";
import {
  HARNESS_GUIDANCE_CUSTOM_TYPE,
  planTextGuidance,
  type TextGuidanceEntry,
} from "./harness-guidance-planner.ts";
import type { ResolvedConfig } from "./guardrail-types.ts";

export interface ContextGuidanceEvent {
  kind: "skill-prompt" | "skill-rule" | "text-rule" | "text-incomplete";
  skill?: string;
  ruleId?: string;
  target?: "system" | "user";
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
    case "user":
      return paths.user;
    case "project":
      return paths.project;
    case "project.local":
      return paths.projectLocal;
    default:
      return "(built-in)";
  }
}

/** Legacy skillPrompts lookup, preserved for existing user files during the
 * format migration. New configurations use flat skill rules instead. */
export function skillPromptTarget(
  event: Pick<BeforeAgentStartEvent, "prompt">,
  config: ResolvedConfig,
): { name: string; prompt: string; target: "system" | "user"; source?: string } | undefined {
  const skill = parseSkillBlock(event.prompt);
  if (!skill) return undefined;
  const guidance = config.skillPrompts?.[skill.name];
  if (!guidance) return undefined;
  if (guidance.userMessagePattern && !new RegExp(guidance.userMessagePattern).test(skill.userMessage ?? "")) {
    return undefined;
  }
  return { name: skill.name, ...guidance };
}

/** Register configured skill and text guidance. */
export default function registerContextGuidance(pi: ExtensionAPI): void {
  pi.registerEntryRenderer("context-guidance-event", (entry, { expanded }, theme) => {
    const details = entry.data as ContextGuidanceEvent | undefined;
    const prompt = safeDisplayText(details?.prompt ?? "context guidance");
    const subject = safeDisplayText(details?.skill ?? details?.ruleId ?? "guidance");
    const label =
      details?.kind === "text-rule"
        ? "text guidance"
        : details?.kind === "text-incomplete"
          ? "text guidance incomplete"
          : details?.kind === "skill-rule"
            ? "skill rule"
            : "skill prompt";
    return createStaticToolLifecycleMessageRenderer({
      createSpec: () =>
        eventToolLifecycle("context", subject, {
          label,
          details: details
            ? [
                details.skill ? `skill=${details.skill}` : `ruleId=${details.ruleId ?? ""}`,
                details.target ? `target=${details.target}` : "",
                `source=${details.source}`,
                `file=${details.file}`,
                "",
                "prompt:",
                prompt,
              ].filter(Boolean)
            : undefined,
        }),
      expandHint: "ctrl+o to expand",
      fit: truncateToWidth,
      visibleWidth,
      wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
      hostComponent: ToolExecutionComponent,
    })({ content: "", details }, { expanded }, theme);
  });

  pi.on("before_agent_start", (event, ctx) => {
    const availableSkills = new Set(event.systemPromptOptions.skills?.map((skill) => skill.name) ?? []);
    const cwd = ctx.cwd || process.cwd();
    const resolved = resolveHarnessConfig(cwd, undefined, availableSkills);
    const skill = parseSkillBlock(event.prompt);

    // Legacy skillPrompts path (unchanged) for existing user files.
    const legacy = skill ? skillPromptTarget(event, resolved.config) : undefined;
    if (legacy) {
      if (legacy.target === "user" && injectedUserPromptContexts.has(ctx)) return undefined;
      if (legacy.target === "user") injectedUserPromptContexts.add(ctx);
      pi.appendEntry("context-guidance-event", {
        kind: "skill-prompt",
        skill: legacy.name,
        target: legacy.target,
        prompt: legacy.prompt,
        source: legacy.source ?? "unknown",
        file: sourceFile(legacy.source, resolved.paths),
      } satisfies ContextGuidanceEvent);
      if (legacy.target === "system") {
        return { systemPrompt: appendSystemGuidance(event.systemPrompt, legacy.prompt) };
      }
      return {
        message: {
          customType: "skill-prompt-guidance",
          content: legacy.prompt,
          display: false,
          details: { skill: legacy.name, target: "user" },
        },
      };
    }

    // New flat-rule path: skill rules + text guidance in one persistent message.
    const skillRules = skill ? evaluateSkill(resolved.config, skill.name) : [];
    let retained: unknown[] = [];
    try {
      retained = buildSessionContext(ctx.sessionManager.buildContextEntries()).messages as unknown[];
    } catch {
      retained = [];
    }
    const textPlan = planTextGuidance(retained, event.prompt, resolved.config);

    if (textPlan.incomplete) {
      pi.appendEntry("context-guidance-event", {
        kind: "text-incomplete",
        prompt: "Text-rule matching did not complete this turn; prior guidance state is preserved.",
        source: "project",
        file: resolved.paths.project,
      } satisfies ContextGuidanceEvent);
    }

    if (skillRules.length === 0 && textPlan.entries.length === 0) return undefined;

    const skillSections = skillRules.map((r) => `[harness:${r.id}] ${r.instructions}`);
    const textSections = textPlan.entries.map((e) => e.text);
    const content = [...skillSections, ...textSections].join("\n\n");

    for (const r of skillRules) {
      pi.appendEntry("context-guidance-event", {
        kind: "skill-rule",
        skill: r.skill,
        ruleId: r.id,
        prompt: r.instructions,
        source: r.source ?? "unknown",
        file: sourceFile(r.source, resolved.paths),
      } satisfies ContextGuidanceEvent);
    }
    for (const e of textPlan.entries) {
      pi.appendEntry("context-guidance-event", {
        kind: "text-rule",
        ruleId: e.id,
        prompt: e.text,
        source: "project",
        file: resolved.paths.project,
      } satisfies ContextGuidanceEvent);
    }

    const details: { entries: TextGuidanceEntry[]; skill?: string; skillRuleIds?: string[] } = {
      entries: textPlan.entries,
    };
    if (skill) details.skill = skill.name;
    if (skillRules.length > 0) details.skillRuleIds = skillRules.map((r) => r.id);

    return {
      message: {
        customType: HARNESS_GUIDANCE_CUSTOM_TYPE,
        content,
        display: false,
        details,
      },
    };
  });
}
