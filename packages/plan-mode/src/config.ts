import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { nonEmpty, parseModelRef } from "@fradser/pi-kit";

export interface PlanModeConfig {
  provider?: string;
  model?: string;
}

const CONFIG_PATH = join(getAgentDir(), "plan-mode.json");

export function readPlanModeConfig(): PlanModeConfig {
  let file: Partial<PlanModeConfig> = {};
  try {
    if (existsSync(CONFIG_PATH)) {
      file = JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as Partial<PlanModeConfig>;
    }
  } catch {
    file = {};
  }

  const envModel = parseModelRef(process.env.PI_PLAN_MODE_MODEL);
  const envProvider = nonEmpty(process.env.PI_PLAN_MODE_PROVIDER);
  return {
    provider: nonEmpty(file.provider) ?? envModel?.provider ?? envProvider,
    model: nonEmpty(file.model) ?? envModel?.model,
  };
}

export function writePlanModeConfig(config: PlanModeConfig): void {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });
  writeFileSync(CONFIG_PATH, `${JSON.stringify(config, null, 2)}\n`, "utf-8");
}

export function planModeConfigPath(): string {
  return CONFIG_PATH;
}
