import type { LearningMode } from "./learning-efficiency";

export type LearningSurface = "memory" | "harness" | "agents";
export type AutomaticPhasePolicy = "apply" | "propose" | "off";
export type PhasePolicies = Record<LearningSurface, AutomaticPhasePolicy>;

export function automaticPhasePolicies(settings: { automaticPhases?: unknown; agentsMd?: { disabled?: boolean } }, mode: LearningMode): PhasePolicies {
  const policies: PhasePolicies = { memory: "apply", harness: "apply", agents: "apply" };
  const raw = settings.automaticPhases;
  if (raw !== undefined) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("automaticPhases must be an object");
    for (const [phase, policy] of Object.entries(raw)) {
      if (!(phase === "memory" || phase === "harness" || phase === "agents") || !(policy === "apply" || policy === "propose" || policy === "off")) {
        throw new Error("automaticPhases accepts memory, harness and agents with apply, propose or off");
      }
      if (mode === "automatic") policies[phase] = policy;
    }
  }
  if (settings.agentsMd?.disabled) policies.agents = "off";
  return policies;
}
