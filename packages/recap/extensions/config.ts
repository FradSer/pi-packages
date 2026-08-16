import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join } from "node:path";

export type RecapLanguage = "auto" | "zh" | "en" | string;

export interface RecapConfig {
  provider?: string;
  model?: string;
  enabled: boolean;
  autoRecap: boolean;
  language: RecapLanguage;
}

function getAgentDir(): string {
  if (process.env.PI_CODING_AGENT_DIR) {
    return process.env.PI_CODING_AGENT_DIR;
  }
  return join(os.homedir(), ".pi", "agent");
}

const CONFIG_PATH = join(getAgentDir(), "recap.json");

function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export function parseModelRef(value: string | undefined): { provider: string; model: string } | undefined {
  const ref = nonEmpty(value);
  if (!ref) return undefined;
  const separator = ref.indexOf("/");
  if (separator <= 0 || separator === ref.length - 1) return undefined;
  return {
    provider: ref.slice(0, separator),
    model: ref.slice(separator + 1),
  };
}

export function modelRef(config: RecapConfig): string | undefined {
  if (config.provider && config.model) return `${config.provider}/${config.model}`;
  return config.model;
}

export function languageLabel(lang: RecapLanguage | undefined): string {
  const l = (lang || "auto").toLowerCase();
  if (l === "auto") return "Auto (same as conversation)";
  if (l === "zh" || l === "zh-cn" || l === "chinese") return "Chinese (\u4E2D\u6587)";
  if (l === "en" || l === "english") return "English";
  return lang || "Auto";
}

export function readRecapConfig(): RecapConfig {
  let file: Partial<RecapConfig> = {};
  try {
    if (existsSync(CONFIG_PATH)) {
      file = JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as Partial<RecapConfig>;
    }
  } catch {
    file = {};
  }

  const envModel = parseModelRef(process.env.PI_RECAP_MODEL);
  const envProvider = nonEmpty(process.env.PI_RECAP_PROVIDER);
  const envModelId = envModel?.model ?? nonEmpty(process.env.PI_RECAP_MODEL);
  const envLang = nonEmpty(process.env.PI_RECAP_LANGUAGE);

  return {
    provider: envModel?.provider ?? envProvider ?? nonEmpty(file.provider),
    model: envModelId ?? nonEmpty(file.model),
    enabled: file.enabled !== false,
    autoRecap: file.autoRecap !== false,
    language: envLang ?? nonEmpty(file.language) ?? "auto",
  };
}

export function writeRecapConfig(config: RecapConfig): void {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });
  writeFileSync(CONFIG_PATH, `${JSON.stringify(config, null, 2)}\n`, "utf-8");
}

export function recapConfigPath(): string {
  return CONFIG_PATH;
}
