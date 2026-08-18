import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { nonEmpty, parseModelRef } from "@fradser/pi-kit";

export interface MemoryConfig {
  provider?: string;
  model?: string;
}

const CONFIG_PATH = join(getAgentDir(), "memory.json");

export function readMemoryConfig(): MemoryConfig {
  let file: Partial<MemoryConfig> = {};
  try {
    if (existsSync(CONFIG_PATH)) {
      file = JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as Partial<MemoryConfig>;
    }
  } catch {
    file = {};
  }

  const envModel = parseModelRef(process.env.PI_MEMORY_MODEL);
  const envProvider = nonEmpty(process.env.PI_MEMORY_PROVIDER);
  const envModelId = envModel?.model ?? nonEmpty(process.env.PI_MEMORY_MODEL);
  return {
    provider: nonEmpty(file.provider) ?? envModel?.provider ?? envProvider,
    model: nonEmpty(file.model) ?? envModelId,
  };
}

export function writeMemoryConfig(config: MemoryConfig): void {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });
  writeFileSync(CONFIG_PATH, `${JSON.stringify(config, null, 2)}\n`, "utf-8");
}

export function memoryConfigPath(): string {
  return CONFIG_PATH;
}
