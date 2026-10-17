/** Harness guidance contributes scoped structured sections at run start.
 * Non-context entries retain delivery evidence. Matching is not compliance.
 */

import {
  buildSessionContext,
  parseSkillBlock,
  keyHint,
  ToolExecutionComponent,
  type EntryRenderer,
  type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldBlock, fieldLine, safeDisplayText } from "@fradser/pi-kit";

import { setRunStartSection } from "./run-start-section.ts";
import { resolveHarnessConfig } from "./guardrail-config.ts";
import { enabledTextRules, evaluateSkill } from "./guardrail-engine.ts";
import {
  HARNESS_GUIDANCE_CUSTOM_TYPE,
  HARNESS_GUIDANCE_ENTRY_TYPE,
  LEGACY_GUIDANCE_ENTRY_TYPE,
  planTextGuidance,
  incompleteTextGuidance,
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

export interface HarnessGuidanceEvent {
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
    case "user.scoped":
      return paths.userScoped;
    case "project":
      return paths.project;
    case "project.local":
      return paths.projectLocal;
    case "built-in defaults":
      return "(built-in)";
    default:
      return "(unknown)";
  }
}

/** Register configured skill and text guidance. */
export default function registerHarnessGuidance(pi: ExtensionAPI): void {
  const renderGuidance: EntryRenderer = (entry, { expanded }, theme) => {
    const details = entry.data as HarnessGuidanceEvent | undefined;
    const prompt = safeDisplayText(details?.prompt ?? "harness guidance");
    const subject = safeDisplayText(details?.skill ?? details?.ruleId ?? "guidance");
    const label =
      details?.kind === "text-rule"
        ? "text guidance"
        : details?.kind === "text-incomplete"
          ? "text guidance incomplete"
          : "skill rule";
    // The full prompt stays visible when expanded: it is the deliverable.
    const promptFields = fieldBlock("prompt", prompt);
    return guidanceRows.message(() => eventToolLifecycle("harness", subject, {
      label,
      tone: details?.kind === "text-incomplete" ? "warning" : "success",
      details: details
        ? [
          fieldLine("source", details.source),
          fieldLine("file", details.file),
          ...promptFields,
        ].filter(Boolean)
        : undefined,
    }))({ content: "", details }, { expanded }, theme);
  };
  pi.registerEntryRenderer(HARNESS_GUIDANCE_ENTRY_TYPE, renderGuidance);
  // Older sessions persisted the previous entry type. Keep it renderable so a
  // retained transcript keeps its guidance view instead of degrading to raw data.
  pi.registerEntryRenderer(LEGACY_GUIDANCE_ENTRY_TYPE, renderGuidance);

  pi.on("context", (event) => ({
    messages: event.messages.filter(message => message.role !== "custom" ||
      ![HARNESS_GUIDANCE_CUSTOM_TYPE, "skill-prompt-guidance", "harness-text-guidance"].includes(message.customType)),
  }));

  pi.on("before_agent_start", (event, ctx) => {
    const availableSkills = new Set(event.systemPromptOptions.skills?.map((skill) => skill.name) ?? []);
    const cwd = ctx.cwd || process.cwd();
    const resolved = resolveHarnessConfig(cwd, undefined, availableSkills);
    const prompt = "prompt" in event ? event.prompt : "";
    const skill = parseSkillBlock(prompt);
    const candidate = skill ? resolved.config.legacy.skillPrompts[skill.name] : undefined;
    const legacy = candidate && (!candidate.userMessagePattern || new RegExp(candidate.userMessagePattern).test(skill?.userMessage ?? "")) ? candidate : undefined;
    if (legacy) pi.appendEntry(HARNESS_GUIDANCE_ENTRY_TYPE, {
      kind: "skill-prompt", skill: skill!.name, target: legacy.target, prompt: legacy.prompt,
      source: legacy.source ?? "unknown", file: sourceFile(legacy.source, resolved.paths),
    } satisfies HarnessGuidanceEvent);
    const skillRules = skill ? evaluateSkill(resolved.config, skill.name) : [];
    let retained: unknown[] = [];
    let delivery: unknown[] = [];
    let contextReadIncomplete = false;
    // The branch ledger is not model context. It records complete scoped text
    // so an incomplete scan cannot silently remove established guidance.
    try {
      delivery = ctx.sessionManager.getBranch().flatMap(entry =>
        entry.type === "custom" && entry.customType === "harness-guidance-delivery"
          ? [{ customType: HARNESS_GUIDANCE_CUSTOM_TYPE, details: entry.data }]
          : entry.type === "custom_message" && entry.customType === HARNESS_GUIDANCE_CUSTOM_TYPE
            ? [{ customType: HARNESS_GUIDANCE_CUSTOM_TYPE, details: entry.details }]
            : []);
    } catch { contextReadIncomplete = true; }
    try {
      if (enabledTextRules(resolved.config).length > 0) {
        retained = buildSessionContext(ctx.sessionManager.buildContextEntries()).messages;
      }
    } catch { contextReadIncomplete = true; }
    const textPlan = contextReadIncomplete
      ? incompleteTextGuidance(delivery)
      : planTextGuidance([...retained, ...delivery], prompt, resolved.config, true);

    if (textPlan.incomplete) {
      pi.appendEntry(HARNESS_GUIDANCE_ENTRY_TYPE, {
        kind: "text-incomplete",
        prompt: textPlan.preservationNotice ?? "Text-rule matching did not complete this turn; prior scoped guidance state is preserved.",
        source: "unknown",
        file: "(unknown)",
      } satisfies HarnessGuidanceEvent);
    }



    const skillSections = skillRules.map((r) =>
      `[harness:${r.id}] Only for this /skill:${r.skill} task; retained history does not extend its scope.\n${r.instructions}`,
    );
    const textSections = textPlan.entries.map((e) => e.text);
    const legacySections = legacy && skill
      ? [`[harness:legacy-skill] Only for this /skill:${skill.name} task; retained history does not extend its scope.\n${legacy.prompt}`]
      : [];
    const content = [...legacySections, ...skillSections, ...textSections].join("\n\n");

    for (const r of skillRules) {
      pi.appendEntry(HARNESS_GUIDANCE_ENTRY_TYPE, {
        kind: "skill-rule",
        skill: r.skill,
        ruleId: r.id,
        prompt: r.instructions,
        source: r.source ?? "unknown",
        file: sourceFile(r.source, resolved.paths),
      } satisfies HarnessGuidanceEvent);
    }
    for (const e of textPlan.entries) {
      pi.appendEntry(HARNESS_GUIDANCE_ENTRY_TYPE, {
        kind: "text-rule",
        ruleId: e.id,
        prompt: e.text,
        source: e.source ?? "unknown",
        file: sourceFile(e.source, resolved.paths),
      } satisfies HarnessGuidanceEvent);
    }

    const details: { entries: TextGuidanceEntry[]; skill?: string; skillRuleIds?: string[] } = {
      entries: textPlan.entries,
    };
    if (skill) details.skill = skill.name;
    if (skillRules.length > 0) details.skillRuleIds = skillRules.map((r) => r.id);

    pi.appendEntry("harness-guidance-delivery", details);
    setRunStartSection(event.systemPromptOptions, "harness_guidance", content);
  });
}
