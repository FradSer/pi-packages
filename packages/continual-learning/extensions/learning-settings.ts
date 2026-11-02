/** Learning controls share the single user-level configuration file
 * (`<agent-dir>/continual-learning.json`) with the learning model, Jev and the
 * capability flags. There is no other settings source and no fallback file. */
import { MAX_AGENTS_MD_FILE_BYTES, MIN_BUDGET_BYTES } from "./agents-md-consolidation";
import { automaticPhasePolicies, type PhasePolicies } from "./learning-controls";
import { readUnifiedConfig, writeUnifiedConfig } from "./config";

export interface MemorySettings {
  autoSettledLearning: boolean;
  autoContinualLearning: boolean;
  automaticPhases?: Partial<PhasePolicies>;
  agentsMd?: { disabled?: boolean; budgetBytes?: number };
  /** Read diagnosis, never persisted as a setting. */
  invalid?: string;
}

function normalizeSettings(raw: Record<string, unknown>): MemorySettings {
  // `autoMemory` is retired and deliberately ignored: it controls neither current trigger.
  // Unrelated sections (model, jev, capability flags) live in the same file and are ignored here.
  for (const key of ["autoSettledLearning", "autoContinualLearning"] as const) {
    if (raw[key] !== undefined && typeof raw[key] !== "boolean") throw new Error(`${key} must be a boolean`);
  }
  let agentsMd: MemorySettings["agentsMd"];
  if (raw.agentsMd !== undefined) {
    if (!raw.agentsMd || typeof raw.agentsMd !== "object" || Array.isArray(raw.agentsMd)) throw new Error("agentsMd must be an object");
    const agents = raw.agentsMd as Record<string, unknown>;
    if (Object.keys(agents).some(key => !["disabled", "budgetBytes"].includes(key))) throw new Error("agentsMd contains unknown fields");
    if (agents.disabled !== undefined && typeof agents.disabled !== "boolean") throw new Error("agentsMd.disabled must be a boolean");
    if (agents.budgetBytes !== undefined && (typeof agents.budgetBytes !== "number" || !Number.isFinite(agents.budgetBytes))) throw new Error("agentsMd.budgetBytes must be finite");
    agentsMd = {
      ...(agents.disabled === true ? { disabled: true } : {}),
      ...(typeof agents.budgetBytes === "number" ? { budgetBytes: Math.min(MAX_AGENTS_MD_FILE_BYTES, Math.max(MIN_BUDGET_BYTES, Math.round(agents.budgetBytes))) } : {}),
    };
  }
  automaticPhasePolicies({ automaticPhases: raw.automaticPhases, agentsMd }, "automatic");
  return {
    autoSettledLearning: raw.autoSettledLearning === true,
    autoContinualLearning: raw.autoContinualLearning === true,
    ...(raw.automaticPhases !== undefined ? { automaticPhases: raw.automaticPhases as Partial<PhasePolicies> } : {}),
    ...(agentsMd ? { agentsMd } : {}),
  };
}

const DEFAULTS: MemorySettings = { autoSettledLearning: false, autoContinualLearning: false };

export async function readLearningSettings(cwd = process.cwd()): Promise<MemorySettings> {
  void cwd; // The unified configuration is user-level, never project-scoped.
  try {
    const unified = readUnifiedConfig();
    if (unified.invalid) throw new Error(unified.invalid);
    if (!unified.record) return DEFAULTS;
    return normalizeSettings(unified.record);
  } catch {
    return { ...DEFAULTS, invalid: "Learning settings could not be read safely or are invalid. Repair continual-learning.json before learning resumes." };
  }
}

export async function writeLearningSettings(settings: MemorySettings): Promise<void> {
  if (settings.invalid) throw new Error(settings.invalid);
  const normalized = normalizeSettings(settings as unknown as Record<string, unknown>);
  // Merge only the fields this module owns; model, Jev and capability flags stay.
  writeUnifiedConfig({
    autoSettledLearning: normalized.autoSettledLearning,
    autoContinualLearning: normalized.autoContinualLearning,
    ...(normalized.automaticPhases !== undefined ? { automaticPhases: normalized.automaticPhases } : {}),
    ...(normalized.agentsMd !== undefined ? { agentsMd: normalized.agentsMd } : {}),
  });
}