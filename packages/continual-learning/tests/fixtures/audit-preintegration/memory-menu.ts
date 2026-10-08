import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { notifyPi, safeDisplayText } from "@fradser/pi-kit";
import type { LearningHistory } from "./learning-history";
import { readLearningFile } from "./learning-history";
import type { MemoryEntry, MemoryLoadResult } from "./memory-files";
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
  loadMemories: (cwd: string) => Promise<MemoryLoadResult>;
  listHistory: (cwd: string) => Promise<LearningHistory[]>;
  manage: (command: string, ctx: ExtensionCommandContext) => Promise<boolean>;
  selectModel: (ctx: ExtensionCommandContext) => Promise<void>;
  toggleAutoMemory: (ctx: ExtensionCommandContext, cwd: string) => Promise<void>;
  isBusy: () => boolean;
}

const FIRST_LEVEL = ["Browse memories", "Learning settings", "Recent learning"] as const;
const MEMORY_DETAIL_MAX_CHARS = 4_000;
const HISTORY_DETAIL_MAX_CHARS = 8_000;

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

function historyOption(record: LearningHistory): string {
  return safeDisplayText(`${record.phase} · ${record.status} · ${record.id}`);
}

function historyDetail(record: LearningHistory): string {
  const lines = [`${record.id} · ${record.phase} · ${record.status} · ${record.createdAt}`];
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
  return bounded(lines.join("\n"), HISTORY_DETAIL_MAX_CHARS);
}

async function browseMemories(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, cwd: string): Promise<void> {
  const memories = await dependencies.loadMemories(cwd);
  if (memories.entries.length === 0) {
    notifyPi(ctx.ui, "No project memories found.", "info");
    return;
  }
  const privateIndex = await privateMemoryIndexState(memories);

  const selected = await ctx.ui.select(
    `Browse memories · ${memories.totalEntries} total${memories.omittedEntries ? ` · ${memories.omittedEntries} omitted from the index` : ""}`,
    memories.entries.map(entry => memoryOption(entry, privateIndex)),
  );
  if (!selected) return;
  const index = memories.entries.findIndex(entry => memoryOption(entry, privateIndex) === selected);
  if (index < 0) return;
  const entry = memories.entries[index];
  notifyPi(ctx.ui, `${memorySource(entry, privateIndex)} · ${entry.filename}\n\n${bounded(entry.content, MEMORY_DETAIL_MAX_CHARS)}`, "info");
  await ctx.ui.select(`Memory entry · ${memorySource(entry, privateIndex)}`, ["Close"]);
}

async function editPolicies(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies): Promise<void> {
  if (dependencies.isBusy()) {
    notifyPi(ctx.ui, "Wait for the current learning pipeline before changing its policy.", "warning");
    return;
  }
  const surfaceLabels = ["Memory policy", "Harness policy", "Agents policy"] as const;
  const surface = await ctx.ui.select("Advanced phase policies", [...surfaceLabels]);
  if (!surface) return;
  const phase = surfaceLabels.findIndex(label => label === surface);
  if (phase < 0) return;
  const policy = await ctx.ui.select(`${surface} · choose behavior`, ["apply", "propose", "off"]);
  if (!policy) return;
  const phases = ["memory", "harness", "agents"] as const;
  await dependencies.manage(`policy ${phases[phase]} ${policy}`, ctx);
}

async function learningSettings(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, cwd: string, status: MemoryMenuStatus): Promise<void> {
  const choice = await ctx.ui.select(
    `Learning settings · auto ${status.autoMemory ? "on" : "off"} · ${safeDisplayText(status.model)}`,
    ["Select learning model", "Toggle automatic learning", "Advanced phase policies"],
  );
  if (!choice) return;
  if (choice === "Select learning model") {
    await dependencies.selectModel(ctx);
  } else if (choice === "Toggle automatic learning") {
    await dependencies.toggleAutoMemory(ctx, cwd);
  } else if (choice === "Advanced phase policies") {
    await editPolicies(ctx, dependencies);
  }
}

async function recentLearning(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies, cwd: string): Promise<void> {
  const records = await dependencies.listHistory(cwd);
  if (records.length === 0) {
    notifyPi(ctx.ui, "No recent learning changes for this project.", "info");
    return;
  }
  const selected = await ctx.ui.select("Recent learning", records.map(historyOption));
  if (!selected) return;
  const record = records.find(item => historyOption(item) === selected);
  if (!record) return;
  notifyPi(ctx.ui, historyDetail(record), "info");

  // Proposed, failed, undone and abandoned records are read-only here. The
  // existing management handler remains the sole owner of undo validation and
  // confirmation for a completed applied change.
  const actions = record.status === "applied" ? ["Close", "Undo this change"] : ["Close"];
  const action = await ctx.ui.select(`Learning change · ${record.status}`, actions);
  if (action !== "Undo this change") return;
  if (dependencies.isBusy()) {
    notifyPi(ctx.ui, "Wait for the current learning pipeline before undoing a change.", "warning");
    return;
  }
  await dependencies.manage(`undo ${record.id}`, ctx);
}

/** Open the compact /memory menu. Empty command handling stays with the root
 * command registration, allowing `/memory <requirement>` to use its existing
 * authoring flow without making this navigation module parse requirements. */
export async function openMemoryMenu(ctx: ExtensionCommandContext, dependencies: MemoryMenuDependencies): Promise<void> {
  const cwd = ctx.cwd || process.cwd();
  try {
    const status = await dependencies.status(cwd);
    if (!ctx.hasUI) {
      notifyPi(ctx.ui, `${statusTitle(status)}. Use /memory with a requirement to add a memory.`, "info");
      return;
    }
    const choice = await ctx.ui.select(statusTitle(status), [...FIRST_LEVEL]);
    if (!choice) return;
    if (choice === "Browse memories") await browseMemories(ctx, dependencies, cwd);
    else if (choice === "Learning settings") await learningSettings(ctx, dependencies, cwd, status);
    else if (choice === "Recent learning") await recentLearning(ctx, dependencies, cwd);
  } catch (error) {
    notifyPi(ctx.ui, `Memory menu failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}
