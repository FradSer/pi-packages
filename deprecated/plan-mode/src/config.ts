import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import * as os from "node:os";
import { dirname, join } from "node:path";
import { nonEmpty, parseModelRef } from "@fradser/pi-kit";

export interface PlanModeConfig {
  provider?: string;
  model?: string;
}

function expandTilde(filepath: string): string {
  if (filepath === "~" || filepath.startsWith("~/")) {
    const home = process.env.HOME ?? os.homedir();
    return join(home, filepath.slice(1));
  }
  return filepath;
}

function getAgentDir(): string {
  if (process.env.PI_CODING_AGENT_DIR) {
    return expandTilde(process.env.PI_CODING_AGENT_DIR);
  }
  return join(process.env.HOME ?? os.homedir(), ".pi", "agent");
}

export function planModeConfigPath(): string {
  return join(getAgentDir(), "plan-mode.json");
}

export function readPlanModeConfig(): PlanModeConfig {
  const configPath = planModeConfigPath();
  let file: Partial<PlanModeConfig> = {};
  try {
    if (existsSync(configPath)) {
      file = JSON.parse(readFileSync(configPath, "utf-8")) as Partial<PlanModeConfig>;
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
  const configPath = planModeConfigPath();
  mkdirSync(dirname(configPath), { recursive: true });
  writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf-8");
}
