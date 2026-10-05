/** Learning controls are separate from model selection and learned knowledge. */
import fs from "node:fs/promises";
import path from "node:path";
import { MAX_AGENTS_MD_FILE_BYTES, MIN_BUDGET_BYTES } from "./agents-md-consolidation";
import { writeFileAtomic } from "./consolidation-run";
import { automaticPhasePolicies, type PhasePolicies } from "./learning-controls";
import { readLearningFile } from "./learning-history";
import { resolveMemoryPaths } from "./memory-paths";

export interface MemorySettings {
  autoMemory: boolean;
  automaticPhases?: Partial<PhasePolicies>;
  agentsMd?: { disabled?: boolean; budgetBytes?: number };
  /** Read diagnosis, never persisted as a setting. */
  invalid?: string;
}

function missing(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT");
}

async function safeSettingsPath(cwd: string): Promise<string> {
  const paths = resolveMemoryPaths(cwd);
  for (const file of [paths.agentDir, path.dirname(paths.settingsFile), paths.settingsFile]) {
    try {
      const stat = await fs.lstat(file);
      if (stat.isSymbolicLink() || (file === paths.settingsFile ? !stat.isFile() : !stat.isDirectory())) throw new Error("Unsafe learning settings path");
    } catch (error) { if (!missing(error)) throw error; }
  }
  return paths.settingsFile;
}

function normalizeSettings(raw: unknown): MemorySettings {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Learning settings must be an object");
  const value = raw as Record<string, unknown>;
  if (Object.keys(value).some(key => !["autoMemory", "automaticPhases", "agentsMd"].includes(key))) throw new Error("Learning settings contain unknown fields");
  if (value.autoMemory !== undefined && typeof value.autoMemory !== "boolean") throw new Error("autoMemory must be a boolean");
  let agentsMd: MemorySettings["agentsMd"];
  if (value.agentsMd !== undefined) {
    if (!value.agentsMd || typeof value.agentsMd !== "object" || Array.isArray(value.agentsMd)) throw new Error("agentsMd must be an object");
    const agents = value.agentsMd as Record<string, unknown>;
    if (Object.keys(agents).some(key => !["disabled", "budgetBytes"].includes(key))) throw new Error("agentsMd contains unknown fields");
    if (agents.disabled !== undefined && typeof agents.disabled !== "boolean") throw new Error("agentsMd.disabled must be a boolean");
    if (agents.budgetBytes !== undefined && (typeof agents.budgetBytes !== "number" || !Number.isFinite(agents.budgetBytes))) throw new Error("agentsMd.budgetBytes must be finite");
    agentsMd = {
      ...(agents.disabled === true ? { disabled: true } : {}),
      ...(typeof agents.budgetBytes === "number" ? { budgetBytes: Math.min(MAX_AGENTS_MD_FILE_BYTES, Math.max(MIN_BUDGET_BYTES, Math.round(agents.budgetBytes))) } : {}),
    };
  }
  automaticPhasePolicies({ automaticPhases: value.automaticPhases, agentsMd }, "automatic");
  return {
    autoMemory: value.autoMemory !== false,
    ...(value.automaticPhases !== undefined ? { automaticPhases: value.automaticPhases as Partial<PhasePolicies> } : {}),
    ...(agentsMd ? { agentsMd } : {}),
  };
}

export async function readLearningSettings(cwd = process.cwd()): Promise<MemorySettings> {
  try {
    const file = await safeSettingsPath(cwd);
    return normalizeSettings(JSON.parse((await readLearningFile(file, 16_384)).toString("utf8")));
  } catch (error) {
    if (missing(error)) return { autoMemory: true };
    return { autoMemory: false, invalid: "Learning settings could not be read safely or are invalid. Repair memory/settings.json before learning resumes." };
  }
}

export async function writeLearningSettings(settings: MemorySettings, cwd = process.cwd()): Promise<void> {
  if (settings.invalid) throw new Error(settings.invalid);
  const normalized = normalizeSettings(settings);
  const file = await safeSettingsPath(cwd);
  await writeFileAtomic(file, `${JSON.stringify(normalized, null, 2)}\n`, 0o600);
}
