import { managementUI, selectMenu, showDetailPages } from "./detail-pages";
import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { notifyPi, safeDisplayText } from "@fradser/pi-kit";
import type { LearningHistory } from "./learning-history";
import { readLearningFile } from "./learning-history";
import type { MemoryEntry, MemoryLoadResult, MemoryLoadOptions } from "./memory-files";
import { parseMemoryIndexLine } from "./consolidation-run";

/** Data shown in the compact /memory title. Keep this separate from settings
 * so the menu does not need to know where the runtime gets its model from. */
export interface MemoryMenuStatus {
  autoMemory: boolean;
  model: string;
  entries: number;
  invalid?: string;
}

/**
 * The menu owns navigation only. Mutations and learning-management semantics
 * stay in the existing extension code and are supplied as typed callbacks.
 * This keeps the UI usable from inject-memory without coupling this module to
 * its long-lived pipeline state.
 */
export interface MemoryMenuDependencies {
  status: (cwd: string) => Promise<MemoryMenuStatus>;
  loadMemories: (cwd: string, options?: MemoryLoadOptions) => Promise<MemoryLoadResult>;
  listHistory: (cwd: string) => Promise<LearningHistory[]>;
  manage: (command: string, ctx: ExtensionCommandContext) => Promise<boolean>;
  selectModel: (ctx: ExtensionCommandContext) => Promise<void>;
  toggleAutoMemory: (ctx: ExtensionCommandContext, cwd: string) => Promise<void>;
  isBusy: () => boolean;
  policies?: (cwd: string) => Promise<{ policies: Record<"memory" | "harness" | "agents", string>; agentsDisabled: boolean }>;
}

const FIRST_LEVEL = ["Browse memories", "Learning settings", "Recent learning"] as const;

function bounded(value: string, limit: number): string {
  const text = safeDisplayText(value);
  return text.length > limit ? `${text.slice(0, limit)}\n[preview clipped]` : text;
}

function statusTitle(status: MemoryMenuStatus): string {
  const state = status.invalid ? "learning unavailable" : `auto ${status.autoMemory ? "on" : "off"}`;
  const count = `${status.entries} ${status.entries === 1 ? "entry" : "entries"}`;
  return `Memory · ${state} · ${safeDisplayText(status.model)} · ${count}`;
}

/**
 * `harness` means the canonical/private root, not necessarily a private
 * memory. Safe entries are mirrored there too. Privacy is established only by
 * the explicit `(harness only)` annotation in that root's index.
 */
interface PrivateMemoryIndexState {
  classifications: Map<string, { name: string; classification: "private" | "safe" }>;
  readable: boolean;
}

const PRIVATE_MARKER_RE = /\(\s*harness[\s_-]+only\s*\)/i;

async function privateMemoryIndexState(memories: MemoryLoadResult): Promise<PrivateMemoryIndexState> {
  const index = memories.indexes.find(item => item.source === "harness" && item.available);
  if (!index) return { classifications: new Map(), readable: false };
  try {
    const text = (await readLearningFile(index.readPath, 64_000)).toString("utf8");
    const classifications = new Map<string, { name: string; classification: "private" | "safe" }>();
    for (const line of text.split(/\r?\n/)) {
      const name = parseMemoryIndexLine(line);
      if (!name) continue;
      const key = name.toLowerCase();
      if (classifications.has(key)) throw new Error(`Duplicate Memory index record: ${name}`);
      classifications.set(key, { name, classification: PRIVATE_MARKER_RE.test(line) ? "private" : "safe" });
    }
    return { classifications, readable: true };
  } catch {
    // An unavailable/stale index cannot prove either privacy or safe sharing.
    return { classifications: new Map(), readable: false };
  }
}

function memorySource(entry: MemoryEntry, privateIndex: PrivateMemoryIndexState): "Private" | "Shared" | "Canonical" {
  if (entry.source !== "harness") return "Shared";
  if (!privateIndex.readable) return "Canonical";
  const classification = privateIndex.classifications.get(entry.filename.toLowerCase());
  if (!classification || classification.name !== entry.filename) return "Canonical";
  return classification.classification === "private" ? "Private" : "Shared";
}

function memoryOption(entry: MemoryEntry, privateIndex: PrivateMemoryIndexState): string {
  const description = entry.description || "(no description)";
  return `${memorySource(entry, privateIndex)} · ${entry.filename} · ${bounded(description, 180).replace(/\s+/g, " ")}`;
}

function historyTarget(record: LearningHistory): string {
  const names = [...new Set(record.changes.map(change => change.target.name))];
  const bodies = names.filter(name => name !== "MEMORY.md");
  // Mirror pairs and index bookkeeping stay in the detail, leaving room for
  // the result in a narrow list row.
  const indexLabel = record.changes.every(change => change.before === null) ? "Index setup" : "Index update";
  const summary = bodies.length ? bodies.join(", ") : names.length ? indexLabel : "saved proposal";
  return summary.length > 28 ? `${summary.slice(0, 27)}…` : summary;
}

function historyOption(record: LearningHistory, index: number): string {
  return safeDisplayText(`#${index + 1} ${historyTarget(record)} · ${record.status} · ${record.createdAt.slice(5, 16).replace("T", " ")} · ${record.phase}`);
}

function historyDetail(record: LearningHistory): string {
  const lines = [`${record.id} · ${record.phase} · ${record.status} · ${record.createdAt}`];
  lines.push(record.batchId ? `Learning batch: ${record.batchId}` : "Recorded before batch tracking");
  for (const change of record.changes) {
    lines.push(`${change.target.root}/${change.target.name}`);
    for (const [label, state] of [["before", change.before], ["after", change.after]] as const) {
      const content = state ? Buffer.from(state.bytes, "base64").toString("utf8") : "(absent)";
      lines.push(`${label}:\n${content}`);
    }
  }
  if (record.status === "proposed" && record.proposal !== undefined) {
    lines.push(`proposal:\n${JSON.stringify(record.proposal, null, 2)}`);
  }
  if (record.status === "proposed") lines.push("Next step: run /consolidate to plan again against current evidence. Saved proposals cannot be applied as stale plans.");
  return safeDisplayText(lines.join("\n"));
}

async function browseMemories(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, cwd: string): Promise<void> {
  // Discovery is intentionally small for model context. Management has its
  // own bounded inventory and reads the selected body only when requested.
  const memories = await dependencies.loadMemories(cwd, {maxFiles:4096, maxFileChars:1024});
  if (memories.entries.length === 0) {
    notifyPi(ctx.ui, "No project memories found.", "info");
    return;
  }
  const privateIndex = await privateMemoryIndexState(memories);
  const pageSize = 32;
  const pages = Math.ceil(memories.entries.length / pageSize);
  let page = 0;
  let selectedIndex = 0;
  for (;;) {
    const entries = memories.entries.slice(page * pageSize, (page + 1) * pageSize);
    const selected = await selectMenu(managementUI(ctx.ui, ctx.mode),
      `Browse memories · ${memories.totalEntries} total${pages > 1 ? ` · page ${page + 1}/${pages}` : ""}${memories.omittedEntries ? ` · ${memories.omittedEntries} unavailable or beyond management limit` : ""}`,
      [...entries.map(entry => memoryOption(entry, privateIndex)), ...(page > 0 ? ["Previous page"] : []), ...(page + 1 < pages ? ["Next page"] : []), "Back"], selectedIndex);
    if (selected === "Next page" && page + 1 < pages) {page++; selectedIndex = 0; continue;}
    if (selected === "Previous page" && page > 0) {page--; selectedIndex = 0; continue;}
    const entry = entries.find(entry => memoryOption(entry, privateIndex) === selected);
    if (!entry) return;
    selectedIndex = entries.indexOf(entry);
    let content = entry.content;
    try { content = (await readLearningFile(entry.readPath, 4 * 1024 * 1024)).toString("utf8"); }
    catch { content += "\n[Full file unavailable; showing the bounded loaded content.]"; }
    await showDetailPages(managementUI(ctx.ui, ctx.mode), `Memory entry · ${memorySource(entry, privateIndex)}`, `${memorySource(entry, privateIndex)} · ${entry.filename}\n${entry.readPath}\n\n${content}`);
  }
}

async function editPolicies(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies): Promise<void> {
  if (dependencies.isBusy()) {
    notifyPi(ctx.ui, "Wait for the current learning pipeline before changing its policy.", "warning");
    return;
  }
  const surfaceLabels = ["Memory policy", "Harness policy", "Agents policy"] as const;
  let selectedIndex = 0;
  for (;;) {
    const surface = await selectMenu(managementUI(ctx.ui, ctx.mode), "Advanced phase policies", [...surfaceLabels], selectedIndex, ["Automatic learning only"]);
    if (!surface) return;
    const phase = surfaceLabels.findIndex(label => label === surface);
    if (phase < 0) return;
    selectedIndex = phase;
    const phaseName = (["memory", "harness", "agents"] as const)[phase];
    const current = await dependencies.policies?.(ctx.cwd || process.cwd());
    const policyLabels = ["apply — save validated changes", "propose — save for review", "off — skip automatic phase"];
    const policy = await selectMenu(managementUI(ctx.ui, ctx.mode), surface, policyLabels,
      Math.max(0, ["apply", "propose", "off"].indexOf(current?.policies[phaseName] ?? "apply")),
      [`Current: ${current?.policies[phaseName] ?? "unknown"} (automatic only)`,
        ...(phaseName === "agents" && current?.agentsDisabled ? ["AGENTS.md disabled overrides this setting"] : []),
        "/consolidate applies validated plans"]);
    const value = policy ? (["apply", "propose", "off"] as const)[policyLabels.indexOf(policy)] : undefined;
    if (!value) continue;
    await dependencies.manage(`policy ${phaseName} ${value}`, ctx);
  }
}

async function learningSettings(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, cwd: string): Promise<void> {
  const actions = ["Select learning model", "Toggle automatic learning", "Advanced phase policies"];
  let selectedIndex = 0;
  for (;;) {
    const current = await dependencies.status(cwd);
    const choice = await selectMenu(managementUI(ctx.ui, ctx.mode), "Learning settings", actions, selectedIndex,
      [`Auto ${current.autoMemory ? "on" : "off"} · ${safeDisplayText(current.model)}`, "Existing Memory retrieval stays on"]);
    if (!choice) return;
    selectedIndex = Math.max(0, actions.indexOf(choice));
    if (choice === "Select learning model") await dependencies.selectModel(ctx);
    else if (choice === "Toggle automatic learning") await dependencies.toggleAutoMemory(ctx, cwd);
    else if (choice === "Advanced phase policies") await editPolicies(ctx, dependencies);
  }
}

async function learningChanges(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, records: LearningHistory[], title = "Recent learning"): Promise<boolean> {
  if (records.length === 0) {
    notifyPi(ctx.ui, "No recent learning changes for this project.", "info");
    return false;
  }
  let selectedIndex = 0;
  for (;;) {
    const selected = await selectMenu(managementUI(ctx.ui, ctx.mode), title, [...records.map(historyOption), "Back"], selectedIndex);
    if (!selected) return false;
    const record = records[records.map(historyOption).indexOf(selected)];
    if (!record) return false;
    selectedIndex = records.indexOf(record);

    // Proposed, failed, undone and abandoned records are read-only here. The
    // existing management handler remains the sole owner of undo validation and
    // confirmation for a completed applied change.
    const actions = record.status === "applied" ? ["Close", "Undo this change"] : ["Close"];
    const action = await showDetailPages(managementUI(ctx.ui, ctx.mode), `Learning change · ${record.status}`, historyDetail(record), actions);
    if (action !== "Undo this change") continue;
    if (dependencies.isBusy()) {
      notifyPi(ctx.ui, "Wait for the current learning pipeline before undoing a change.", "warning");
      return false;
    }
    await dependencies.manage(`undo ${record.id}`, ctx);
    return true;
  }
}

async function recentLearning(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, cwd: string): Promise<void> {
  const records = await dependencies.listHistory(cwd);
  if (!records.some(record => record.batchId)) {
    await learningChanges(ctx, dependencies, records);
    return;
  }
  const groups = new Map<string, LearningHistory[]>();
  for (const record of records) {
    const key = record.batchId ?? record.id;
    groups.set(key, [...(groups.get(key) ?? []), record]);
  }
  const batches = [...groups.values()];
  const options = batches.map((batch, index) => {
    const counts = new Map<string, number>();
    for (const record of batch) counts.set(record.status, (counts.get(record.status) ?? 0) + 1);
    const state = [...counts].map(([status, count]) => `${count} ${status}`).join(", ");
    const primary = batch.find(record => record.phase === "memory" && record.changes.some(change => change.target.name !== "MEMORY.md")) ?? batch[0];
    return batch[0].batchId ? `#${index + 1} ${historyTarget(primary)} · ${state}` : historyOption(primary, index);
  });
  let selectedIndex = 0;
  for (;;) {
    const selected = await selectMenu(managementUI(ctx.ui, ctx.mode), "Learning batches", [...options, "Back"], selectedIndex,
      ["One learning can create several file changes.", "Inspect and undo each change separately."]);
    if (!selected || selected === "Back") return;
    selectedIndex = options.indexOf(selected);
    if (selectedIndex < 0) return;
    if (await learningChanges(ctx, dependencies, batches[selectedIndex], "Learning batch changes")) return;
  }
}

/** Open the compact /memory menu. Empty command handling stays with the root
 * command registration, allowing `/memory <requirement>` to use its existing
 * authoring flow without making this navigation module parse requirements. */
export async function openMemoryMenu(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies): Promise<void> {
  const cwd = ctx.cwd || process.cwd();
  try {
    for (;;) {
      const status = await dependencies.status(cwd);
      if (!ctx.hasUI) {
        notifyPi(ctx.ui, `${statusTitle(status)}. Use /memory with a requirement to add a memory.`, "info");
        return;
      }
      const choice = await ctx.ui.select(statusTitle(status), [...FIRST_LEVEL, "Close"]);
      if (!choice || choice === "Close") return;
      if (choice === "Browse memories") await browseMemories(ctx, dependencies, cwd);
      else if (choice === "Learning settings") await learningSettings(ctx, dependencies, cwd);
      else if (choice === "Recent learning") await recentLearning(ctx, dependencies, cwd);
    }
  } catch (error) {
    notifyPi(ctx.ui, `Memory menu failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}
