import path from "node:path";
import type { ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { notifyPi, safeDisplayText } from "@fradser/pi-kit";
import { automaticPhasePolicies, type PhasePolicies } from "./learning-controls";
import { listLearningHistory, previewLearningUndo, readLearningFile, readLearningHistory, undoLearningChange, type LearningHistory } from "./learning-history";
import { evaluateLearningRules } from "./learning-evaluation";

interface ManagedSettings { autoMemory: boolean; automaticPhases?: Partial<PhasePolicies>; agentsMd?: { disabled?: boolean } }
interface ManagementDependencies<T extends ManagedSettings> {
  readSettings: (cwd: string) => Promise<T>;
  writeSettings: (settings: T, cwd: string) => Promise<void>;
  busy: () => boolean;
}

function describe(record: LearningHistory): string {
  const lines = [`${record.id} · ${record.phase} · ${record.status} · ${record.createdAt}`];
  for (const change of record.changes) {
    lines.push(`${change.target.root}/${change.target.name}`);
    for (const [label, state] of [["before", change.before], ["after", change.after]] as const) {
      const text = state ? Buffer.from(state.bytes, "base64").toString("utf8") : "(absent)";
      lines.push(`${label}:\n${text.slice(0, 1600)}${text.length > 1600 ? "\n[preview clipped]" : ""}`);
    }
  }
  if (record.status === "proposed") lines.push(JSON.stringify(record.proposal, null, 2));
  const text = safeDisplayText(lines.join("\n"));
  return text.length > 12_000 ? `${text.slice(0, 12_000)}\n[preview clipped; inspect individual source files before undo]` : text;
}

export async function handleLearningManagement<T extends ManagedSettings>(command: string, ctx: ExtensionCommandContext, dependencies: ManagementDependencies<T>): Promise<boolean> {
  const [verb, ...args] = command.split(/\s+/);
  if (!["policy", "history", "undo", "evaluate"].includes(verb)) return false;
  const cwd = ctx.cwd || process.cwd();
  try {
    if (verb === "policy") {
      const settings = await dependencies.readSettings(cwd);
      if (args.length === 0) {
        const policies = automaticPhasePolicies(settings, "automatic");
        notifyPi(ctx.ui, Object.entries(policies).map(([phase, policy]) => `${phase}: ${policy}`).join("\n") + "\nSet with /memory policy <memory|harness|agents> <apply|propose|off>. Explicit /consolidate applies current validated plans; agentsMd.disabled still takes precedence.", "info");
      } else {
        if (args.length !== 2 || !["memory", "harness", "agents"].includes(args[0]) || !["apply", "propose", "off"].includes(args[1])) throw new Error("Usage: /memory policy <memory|harness|agents> <apply|propose|off>");
        if (dependencies.busy()) throw new Error("Wait for the current learning pipeline before changing its policy");
        const next = { ...settings, automaticPhases: { ...settings.automaticPhases, [args[0]]: args[1] } };
        automaticPhasePolicies(next, "automatic");
        await dependencies.writeSettings(next, cwd);
        notifyPi(ctx.ui, `Automatic ${args[0]}: ${args[1]}`, "info");
      }
    } else if (verb === "history") {
      if (args.length > 1) throw new Error("Usage: /memory history [change-id]");
      if (args[0]) notifyPi(ctx.ui, describe(await readLearningHistory(cwd, args[0])), "info");
      else {
        const records = await listLearningHistory(cwd);
        notifyPi(ctx.ui, records.length ? records.map(record => `${record.id} · ${record.phase} · ${record.status} · ${record.changes.length} file(s)`).join("\n") : "No learning history for this project.", "info");
      }
    } else if (verb === "undo") {
      if (!args[0] || args.length > 2 || (args[1] !== undefined && args[1] !== "--yes")) throw new Error("Usage: /memory undo <change-id> [--yes]");
      if (dependencies.busy()) throw new Error("Wait for the current learning pipeline before undo");
      const preview = await previewLearningUndo(cwd, args[0]);
      const description = describe(preview.record);
      if (args[1] !== "--yes") {
        if (!ctx.hasUI) throw new Error("Headless undo requires the exact change id and --yes after inspecting /memory history <change-id>");
        if (!(await ctx.ui.confirm("Restore this learning change's predecessors?", description))) return true;
      }
      await undoLearningChange(cwd, args[0], preview.digest);
      notifyPi(ctx.ui, `Undone ${args[0]}. Later edits were checked before restoration.`, "info");
    } else {
      const file = command.slice("evaluate".length).trim();
      if (!file) throw new Error("Usage: /memory evaluate <suite.json>");
      const suite = JSON.parse((await readLearningFile(path.resolve(cwd, file), 1_000_000)).toString("utf8"));
      const result = evaluateLearningRules(suite, suite.baseline, suite.candidate);
      notifyPi(ctx.ui, safeDisplayText(JSON.stringify(result, null, 2)), "info");
    }
  } catch (error) {
    notifyPi(ctx.ui, `Learning ${verb} failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
  return true;
}
