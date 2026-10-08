import { showDetailPages } from "./detail-pages";
import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import { safeDisplayText } from "@fradser/pi-kit";
import type { ConfigPaths } from "./guardrail-config.ts";
import type { ResolvedHarnessConfig, Rule } from "./guardrail-types.ts";

const RULES_PER_PAGE = 20;
const MAX_DISPLAY_CHARS = 2_000;

type HarnessMenuUI = Pick<ExtensionUIContext, "select" | "input" | "notify">;
export type HarnessMenuScope = "project" | "project.local" | "user";

export interface HarnessMenuRequest {
  request: string;
  scope: HarnessMenuScope;
}

function display(value: unknown, limit = MAX_DISPLAY_CHARS): string {
  const text = safeDisplayText(value).replace(/\r\n?/g, "\n");
  return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}…` : text;
}

function label(value: unknown, limit = 120): string {
  return display(value, limit).replace(/\n/g, " ");
}

function ruleKind(rule: Rule): string {
  if ("skill" in rule) return `skill:${label(rule.skill)}`;
  if ("bash" in rule) return `bash:${label(rule.bash)}`;
  if ("text" in rule) return `text:${label(rule.text)}`;
  return "disabled";
}

function ruleLabel(rule: Rule): string {
  const state = rule.enabled === false ? " · disabled" : "";
  return `${label(rule.id)} · ${ruleKind(rule)}${state}`;
}

function uniqueRuleLabels(rules: readonly Rule[]): string[] {
  const bases = rules.map(ruleLabel);
  const counts = new Map<string, number>();
  for (const base of bases) counts.set(base, (counts.get(base) ?? 0) + 1);
  const seen = new Map<string, number>();
  return bases.map((base) => {
    if ((counts.get(base) ?? 0) === 1) return base;
    const ordinal = (seen.get(base) ?? 0) + 1;
    seen.set(base, ordinal);
    return `${base} · #${ordinal}`;
  });
}

function ruleDetails(rule: Rule, paths: ConfigPaths): string {
  const source = rule.source === "user"
    ? paths.user
    : rule.source === "user.scoped"
      ? paths.userScoped
      : rule.source === "project.local"
        ? paths.projectLocal
        : rule.source === "project"
          ? paths.project
          : rule.source ?? "(built-in)";
  const body = "bash" in rule
    ? [`pattern: ${safeDisplayText(rule.bash)}`, `action: ${display(rule.action ?? "pass + message", 80)}`, `message: ${safeDisplayText(rule.message)}`]
    : "skill" in rule
      ? [`skill: ${display(rule.skill, 160)}`, `guidance: ${safeDisplayText(rule.instructions)}`]
      : "text" in rule
        ? [`pattern: ${safeDisplayText(rule.text)}`, `guidance: ${safeDisplayText(rule.instructions)}`]
        : ["This rule is disabled."];
  return safeDisplayText([`rule: ${label(rule.id, 160)}`, `source: ${safeDisplayText(source)}`, `state: ${rule.enabled === false ? "disabled" : "enabled"}`, ...body].join("\n"));
}

function scopeFromChoice(choice: string): HarnessMenuScope | undefined {
  if (choice === "Project shared (default)") return "project";
  if (choice === "Project personal") return "project.local";
  if (choice === "Global shared") return "user";
  return undefined;
}

async function requestRule(ui: HarnessMenuUI, onRequest: (request: HarnessMenuRequest) => Promise<void> | void): Promise<void> {
  const scopeChoice = await ui.select("Where should this rule live?", [
    "Project shared (default)",
    "Project personal",
    "Global shared",
    "Cancel",
  ]);
  const scope = scopeFromChoice(scopeChoice ?? "");
  if (!scope) return;
  const request = (await ui.input("Create or update a Harness rule", ""))?.trim();
  if (!request) return;
  await onRequest({ request, scope });
}

function hasDiagnostics(config: ResolvedHarnessConfig): boolean {
  return config.errors.length > 0
    || config.notices.length > 0
    || config.invalidRules.length > 0
    || config.legacy.policies.length > 0
    || config.legacy.invalidPolicies.length > 0
    || Object.keys(config.legacy.skillPrompts).length > 0
    || config.legacy.disabled.length > 0
    || config.legacy.unavailable
    || config.configReadIncomplete
    || !config.bashEvaluationComplete;
}

function diagnosticsText(config: ResolvedHarnessConfig): string {
  const lines = ["Harness diagnostics"];
  if (config.errors.length) lines.push("errors:", ...config.errors.slice(0, 8).map(error => `- ${display(error, 600)}`));
  if (config.notices.length) lines.push("notices:", ...config.notices.slice(0, 8).map(notice => `- ${display(notice, 600)}`));
  if (config.invalidRules.length) lines.push("invalid rules:", ...config.invalidRules.slice(0, 8).map(rule => `- ${label(rule.id)}: ${display(rule.errors.join("; "), 600)}`));
  if (config.legacy.policies.length) lines.push(`legacy policies: ${config.legacy.policies.length} (read-only)`);
  if (config.legacy.invalidPolicies.length) lines.push(`invalid legacy policies: ${config.legacy.invalidPolicies.length}`);
  if (Object.keys(config.legacy.skillPrompts).length) lines.push(`legacy skill guidance: ${Object.keys(config.legacy.skillPrompts).length} (read-only)`);
  if (config.legacy.disabled.length) lines.push(`legacy disabled identities: ${config.legacy.disabled.length} (read-only)`);
  if (config.legacy.unavailable) lines.push("legacy configuration is unavailable");
  if (config.configReadIncomplete) lines.push("configuration read is incomplete; missing layers remain indeterminate");
  if (!config.bashEvaluationComplete) lines.push("Bash evaluation is incomplete until the affected configuration is repaired");
  return display(lines.join("\n"), 8_000);
}

/** Run the small interactive Harness surface. All content is bounded and sanitized. */
export async function runHarnessMenu(
  ui: HarnessMenuUI,
  config: ResolvedHarnessConfig,
  paths: ConfigPaths,
  onRequest: (request: HarnessMenuRequest) => Promise<void> | void,
): Promise<void> {
  const pageCount = Math.max(1, Math.ceil(config.rules.length / RULES_PER_PAGE));
  let page = 0;
  while (true) {
    const visibleRules = config.rules.slice(page * RULES_PER_PAGE, (page + 1) * RULES_PER_PAGE);
    const labels = uniqueRuleLabels(visibleRules);
    const navigation = [
      ...(page > 0 ? ["Previous page"] : []),
      ...(page + 1 < pageCount ? ["Next page"] : []),
    ];
    const actions = ["Create or update rule", ...(hasDiagnostics(config) ? ["View diagnostics"] : []), "Close"];
    const title = pageCount > 1 ? `Harness rules · page ${page + 1}/${pageCount} · ${config.rules.length} rules` : "Harness rules";
    const choice = await ui.select(title, [...labels, ...navigation, ...actions]);
    if (!choice || choice === "Close") return;
    if (choice === "Next page") {
      page = Math.min(page + 1, pageCount - 1);
      continue;
    }
    if (choice === "Previous page") {
      page = Math.max(page - 1, 0);
      continue;
    }
    if (choice === "View diagnostics") {
      await showDetailPages(ui, "Harness diagnostics", diagnosticsText(config), ["Close"], "warning");
      return;
    }
    if (choice === "Create or update rule") {
      await requestRule(ui, onRequest);
      return;
    }
    const selectedIndex = labels.indexOf(choice);
    if (selectedIndex < 0) return;
    const selected = visibleRules[selectedIndex];
    if (!selected) return;
    const next = await showDetailPages(ui, `Harness rule: ${label(selected.id)}`, ruleDetails(selected, paths), ["Create or update rule", "Close"]);
    if (next === "Create or update rule") await requestRule(ui, onRequest);
    return;
  }
}
