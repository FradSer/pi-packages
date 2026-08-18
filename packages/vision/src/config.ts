import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { nonEmpty, parseModelRef } from "@fradser/pi-kit";

export interface VisionConfig {
  provider?: string;
  model?: string;
  enabled: boolean;
}

const CONFIG_PATH = join(getAgentDir(), "vision.json");

export function readVisionConfig(): VisionConfig {
  let file: Partial<VisionConfig> = {};
  try {
    if (existsSync(CONFIG_PATH)) {
      file = JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as Partial<VisionConfig>;
    }
  } catch {
    file = {};
  }

  const envModel = parseModelRef(process.env.PI_VISION_MODEL);
  const envProvider = nonEmpty(process.env.PI_VISION_PROVIDER);
  const envModelId = envModel?.model ?? nonEmpty(process.env.PI_VISION_MODEL);
  return {
    provider: nonEmpty(file.provider) ?? envModel?.provider ?? envProvider,
    model: nonEmpty(file.model) ?? envModelId,
    enabled: file.enabled !== false,
  };
}

export function writeVisionConfig(config: VisionConfig): void {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });
  writeFileSync(CONFIG_PATH, `${JSON.stringify(config, null, 2)}\n`, "utf-8");
}

export function visionConfigPath(): string {
  return CONFIG_PATH;
}
