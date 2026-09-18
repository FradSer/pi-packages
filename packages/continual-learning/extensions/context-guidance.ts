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
  keyHint,
  ToolExecutionComponent,
  type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldBlock, fieldLine, safeDisplayText } from "@fradser/pi-kit";

import { resolveHarnessConfig } from "./guardrail-config.ts";
import { evaluateSkill } from "./guardrail-engine.ts";
import {
  HARNESS_GUIDANCE_CUSTOM_TYPE,
  planTextGuidance,
  type TextGuidanceEntry,
} from "./harness-guidance-planner.ts";

/** Geometry bound once: every guidance row shares hint and wrapping. */
const guidanceRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});

export interface ContextGuidanceEvent {
  kind: "skill-prompt" | "skill-rule" | "text-rule" | "text-incomplete";
  target?: "system" | "user";
  skill?: string;
  ruleId?: string;
  prompt: string;
  source: string;
  file: string;
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
          : "skill rule";
    // The full prompt stays visible when expanded: it is the deliverable.
    const promptFields = fieldBlock("prompt", prompt, Number.POSITIVE_INFINITY);
    return guidanceRows.message(() => eventToolLifecycle("harness", subject, {
      label,
      detailLimit: "all",
      details: details
        ? [
          fieldLine("source", details.source),
          fieldLine("file", details.file),
          ...promptFields,
        ].filter(Boolean)
        : undefined,
    }))({ content: "", details }, { expanded }, theme);
  });

  pi.on("before_agent_start", (event, ctx) => {
    const availableSkills = new Set(event.systemPromptOptions.skills?.map((skill) => skill.name) ?? []);
    const cwd = ctx.cwd || process.cwd();
    const resolved = resolveHarnessConfig(cwd, undefined, availableSkills);
    const skill = parseSkillBlock(event.prompt);
    const candidate = skill ? resolved.config.legacy.skillPrompts[skill.name] : undefined;
    const legacy = candidate && (!candidate.userMessagePattern || new RegExp(candidate.userMessagePattern).test(skill?.userMessage ?? "")) ? candidate : undefined;
    if (legacy) pi.appendEntry("context-guidance-event", {
      kind: "skill-prompt", skill: skill!.name, target: legacy.target, prompt: legacy.prompt,
      source: legacy.source ?? "unknown", file: sourceFile(legacy.source, resolved.paths),
    } satisfies ContextGuidanceEvent);
    const systemPrompt = legacy?.target === "system"
      ? event.systemPrompt.includes(legacy.prompt) ? event.systemPrompt : `${event.systemPrompt}${event.systemPrompt ? "\n\n" : ""}${legacy.prompt}`
      : undefined;

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

    if (skillRules.length === 0 && textPlan.entries.length === 0 && legacy?.target !== "user") return systemPrompt === undefined ? undefined : { systemPrompt };

    const skillSections = skillRules.map((r) =>
      `[harness:${r.id}] Only for this /skill:${r.skill} task; retained history does not extend its scope.\n${r.instructions}`,
    );
    const textSections = textPlan.entries.map((e) => e.text);
    const content = [...(legacy?.target === "user" ? [legacy.prompt] : []), ...skillSections, ...textSections].join("\n\n");

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
      ...(systemPrompt === undefined ? {} : { systemPrompt }),
      message: {
        customType: HARNESS_GUIDANCE_CUSTOM_TYPE,
        content,
        display: false,
        details,
      },
    };
  });
}
