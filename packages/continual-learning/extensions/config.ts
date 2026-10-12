import { randomBytes } from "node:crypto";
import {
  closeSync,
  constants as fsConstants,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { nonEmpty, parseModelRef } from "@fradser/pi-kit";

export interface MemoryConfig {
  provider?: string;
  model?: string;
}

export interface MemoryConfigState {
  config: MemoryConfig;
  invalid?: string;
  present: boolean;
}

function configRoot(): string {
  return resolve(getAgentDir());
}

function configPath(): string {
  return join(configRoot(), "memory.json");
}

function isMissing(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT");
}

function lstatIfPresent(pathname: string): ReturnType<typeof lstatSync> | undefined {
  try {
    return lstatSync(pathname);
  } catch (error) {
    if (isMissing(error)) return undefined;
    throw error;
  }
}

function assertNoSymlinkComponents(pathname: string): void {
  const absolute = resolve(pathname);
  // Walk every component so an intermediate symlink cannot route the agent
  // directory outside its lexical location (e.g. PI_CODING_AGENT_DIR
  // = /tmp/link/subdir where /tmp/link -> /tmp/outside). Existing OS
  // top-level symlinks such as /var -> private/var and /tmp -> private/tmp
  // on macOS are expected and must not be rejected.
  const parts = absolute.split("/").filter(Boolean);
  let current = "/";
  for (const part of parts) {
    current = join(current, part);
    if (current === "/var" || current === "/tmp") {
      const stat = lstatIfPresent(current);
      if (stat?.isSymbolicLink()) continue;
    }
    const stat = lstatIfPresent(current);
    if (stat?.isSymbolicLink()) throw new Error(`Memory config path is symlinked: ${current}`);
    if (stat !== undefined) continue;
  }
}

function assertSafeAgentDir(create: boolean): string {
  const root = configRoot();
  assertNoSymlinkComponents(root);
  if (!lstatIfPresent(root)) {
    if (!create) return root;
    mkdirSync(root, { recursive: true });
  }
  const stat = lstatSync(root);
  if (stat.isSymbolicLink()) throw new Error(`Memory config root is symlinked: ${root}`);
  if (!stat.isDirectory()) throw new Error(`Memory config root is not a directory: ${root}`);
  assertNoSymlinkComponents(root);
  return root;
}

function assertSafeConfigTarget(file: string): void {
  const stat = lstatIfPresent(file);
  if (!stat) return;
  if (stat.isSymbolicLink()) throw new Error(`Memory config target is symlinked: ${file}`);
  if (!stat.isFile()) throw new Error(`Memory config target is not a regular file: ${file}`);
}

function validPair(provider: unknown, model: unknown): MemoryConfig | undefined {
  if ((provider !== undefined && (typeof provider !== "string" || !provider.trim())) ||
      (model !== undefined && (typeof model !== "string" || !model.trim()))) return undefined;
  const p = nonEmpty(provider);
  const m = nonEmpty(model);
  if (!p && !m) return {};
  if (!p || !m) return undefined;
  return { provider: p, model: m };
}

function readFileConfig(raw: string): MemoryConfigState {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return { config: {}, invalid: "memory.json is not valid JSON", present: true };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { config: {}, invalid: "memory.json must contain an object", present: true };
  }
  const record = value as Record<string, unknown>;
  const config = validPair(record.provider, record.model);
  if (!config) {
    return { config: {}, invalid: "memory.json must contain provider and model together", present: true };
  }
  if (Object.keys(record).some((key) => key !== "provider" && key !== "model")) {
    return { config, invalid: "memory.json contains unknown fields", present: true };
  }
  return { config, present: true };
}

function readEnvironmentConfig(): MemoryConfigState {
  const rawModel = nonEmpty(process.env.PI_MEMORY_MODEL);
  const rawProvider = nonEmpty(process.env.PI_MEMORY_PROVIDER);
  if (!rawModel && !rawProvider) return { config: {}, present: false };
  const parsed = parseModelRef(rawModel);
  if (parsed) return { config: parsed, present: false };
  const pair = validPair(rawProvider, rawModel);
  if (pair && pair.provider && pair.model) return { config: pair, present: false };
  return { config: {}, invalid: "memory model configuration must be provider/model", present: false };
}

export function readMemoryConfigState(): MemoryConfigState {
  try {
    const file = configPath();
    const root = assertSafeAgentDir(false);
    const target = join(root, "memory.json");
    if (!lstatIfPresent(target)) return readEnvironmentConfig();
    assertSafeConfigTarget(target);
    return readFileConfig(readFileSync(file, "utf8"));
  } catch (error) {
    if (isMissing(error)) return readEnvironmentConfig();
    return { config: {}, invalid: "memory.json could not be read safely", present: true };
  }
}

function writeAll(fd: number, bytes: Buffer): void {
  let offset = 0;
  while (offset < bytes.length) {
    const written = writeSync(fd, bytes, offset, bytes.length - offset);
    if (written <= 0) throw new Error("Memory config write made no progress");
    offset += written;
  }
}

export function writeMemoryConfig(config: MemoryConfig): void {
  const normalized = validPair(config.provider, config.model);
  if (!normalized || !normalized.provider || !normalized.model) {
    throw new Error("Memory model must include provider and model together.");
  }
  const root = assertSafeAgentDir(true);
  const file = join(root, "memory.json");
  assertSafeConfigTarget(file);
  const temporary = join(root, `.memory.json.${process.pid}.${randomBytes(12).toString("hex")}.tmp`);
  const bytes = Buffer.from(`${JSON.stringify(normalized, null, 2)}\n`, "utf8");
  let fd: number | undefined;
  try {
    fd = openSync(
      temporary,
      fsConstants.O_WRONLY |
        fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o600,
    );
    writeAll(fd, bytes);
    fsyncSync(fd);
    closeSync(fd);
    fd = undefined;
    assertSafeAgentDir(true);
    assertSafeConfigTarget(file);
    renameSync(temporary, file);
  } catch (error) {
    if (fd !== undefined) closeSync(fd);
    try {
      unlinkSync(temporary);
    } catch {
      // The temporary file may not have been created or may already be renamed.
    }
    throw error;
  }
}

export function memoryConfigPath(): string {
  return configPath();
}

export type JevStage = "selection" | "memory" | "harness";
export interface JevLearningConfig {
  model: string;
  /** Grants semantic participation only, never file-write authority. */
  scopes: JevStage[];
  allowPrivateMemory?: boolean;
  apiKey?: string;
}
export interface JevConfigState {
  config?: JevLearningConfig;
  invalid?: "invalid-config";
  disabled?: boolean;
}

/** User-level opt-in, using the same safe file boundaries as memory.json.
 * Reads only the Jev section; unrelated unified configuration is preserved. */
export function readJevConfigState(): JevConfigState {
  try {
    const root = assertSafeAgentDir(false);
    const file = join(root, "continual-learning.json");
    if (!lstatIfPresent(file)) return {};
    assertSafeConfigTarget(file);
    if (lstatSync(file).size > 4096) return { invalid: "invalid-config" };
    const raw: unknown = JSON.parse(readFileSync(file, "utf8"));
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { invalid: "invalid-config" };
    const jev = (raw as Record<string, unknown>).jev;
    if (jev === undefined) return {};
    if (jev === false) return { disabled: true };
    if (jev !== true && (!jev || typeof jev !== "object" || Array.isArray(jev))) return { invalid: "invalid-config" };
    const value = (jev === true ? {} : jev) as Record<string, unknown>;
    if (Object.keys(value).some(key => !["model", "scopes", "enabled", "allowPrivateMemory", "apiKey"].includes(key))
      || (value.enabled !== undefined && typeof value.enabled !== "boolean")
      || (value.apiKey !== undefined && (typeof value.apiKey !== "string" || !value.apiKey.trim()))
      || (value.allowPrivateMemory !== undefined && typeof value.allowPrivateMemory !== "boolean")) return { invalid: "invalid-config" };
    const model = value.model ?? "jev-1.13.0";
    const scopes = value.scopes ?? ["selection", "memory", "harness"];
    if (typeof model !== "string" || !/^(?:jev-[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|jev-latest|jev-preview)$/.test(model)
      || !Array.isArray(scopes) || scopes.length < 1 || scopes.length > 3
      || !scopes.every(scope => ["selection", "memory", "harness"].includes(scope))
      || new Set(scopes).size !== scopes.length) return { invalid: "invalid-config" };
    if (value.enabled === false) return { disabled: true };
    return { config: { model, scopes: scopes as JevStage[], allowPrivateMemory: value.allowPrivateMemory === true,
      ...(typeof value.apiKey === "string" ? { apiKey: value.apiKey } : {}) } };
  } catch {
    return { invalid: "invalid-config" };
  }
}

/** Explicit capability opt-in for a verified learning-model gateway. */
export function plannerJsonOutputEnabled(): boolean {
  try {
    const file = join(assertSafeAgentDir(false), "continual-learning.json");
    if (!lstatIfPresent(file)) return false;
    assertSafeConfigTarget(file);
    if (lstatSync(file).size > 4096) return false;
    const raw: unknown = JSON.parse(readFileSync(file, "utf8"));
    return !!raw && typeof raw === "object" && !Array.isArray(raw)
      && (raw as Record<string, unknown>).plannerJsonOutput === true;
  } catch { return false; }
}
