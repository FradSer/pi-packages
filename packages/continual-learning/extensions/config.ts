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

/** The single user-level package configuration: learning model, learning
 * triggers, phase policies, Jev and the capability flags share one file. */
const UNIFIED_CONFIG_MAX_BYTES = 4096;
function unifiedConfigPath(): string {
  return join(configRoot(), "continual-learning.json");
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

export interface UnifiedConfigState {
  record?: Record<string, unknown>;
  present: boolean;
  invalid?: string;
}

/** Read the single user-level configuration file with the package's path rules. */
export function readUnifiedConfig(): UnifiedConfigState {
  const file = unifiedConfigPath();
  if (!lstatIfPresent(file)) return { present: false };
  try {
    assertSafeConfigTarget(file);
    if (lstatSync(file).size > UNIFIED_CONFIG_MAX_BYTES) {
      return { present: true, invalid: "continual-learning.json exceeds 4096 bytes" };
    }
    const raw: unknown = JSON.parse(readFileSync(file, "utf8"));
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return { present: true, invalid: "continual-learning.json must contain an object" };
    }
    return { present: true, record: raw as Record<string, unknown> };
  } catch (error) {
    return { present: true, invalid: error instanceof SyntaxError
      ? "continual-learning.json is not valid JSON"
      : "continual-learning.json could not be read safely" };
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

function writeConfigAtomically(temporary: string, file: string, bytes: Buffer): void {
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

/** Merge `patch` into continual-learning.json, preserving every other section.
 * An unparseable predecessor is never clobbered: the user repairs it first. */
export function writeUnifiedConfig(patch: Record<string, unknown>): void {
  const root = assertSafeAgentDir(true);
  const file = unifiedConfigPath();
  assertSafeConfigTarget(file);
  let next: Record<string, unknown> = {};
  const current = readUnifiedConfig();
  if (current.invalid) {
    throw new Error(`${current.invalid}; repair it before writing continual-learning.json`);
  }
  if (current.record) next = current.record;
  Object.assign(next, patch);
  const temporary = join(root, `.continual-learning.json.${process.pid}.${randomBytes(12).toString("hex")}.tmp`);
  const bytes = Buffer.from(`${JSON.stringify(next, null, 2)}\n`, "utf8");
  writeConfigAtomically(temporary, file, bytes);
}

export function readMemoryConfigState(): MemoryConfigState {
  try {
    assertSafeAgentDir(false);
    // The unified file is the only configuration source; an invalid model field
    // surfaces instead of silently falling back to the session model.
    const unified = readUnifiedModelState();
    if (unified.invalid) return { config: {}, invalid: unified.invalid, present: true };
    if (unified.model) return { config: unified.model, present: true };
    // A present unified file is authoritative even when it sets no model.
    if (unified.present) return { config: {}, present: true };
    return readEnvironmentConfig();
  } catch (error) {
    if (isMissing(error)) return readEnvironmentConfig();
    return { config: {}, invalid: "memory model configuration could not be read safely", present: true };
  }
}

/** Read only the unified file's learning model. Absence of the file or of its
 * `model` key is not an error: the environment override or the session model
 * follows. */
function readUnifiedModelState(): { model?: MemoryConfig; invalid?: string; present: boolean } {
  const state = readUnifiedConfig();
  if (state.invalid) return { present: true, invalid: state.invalid };
  if (!state.record) return { present: false };
  const value = state.record.model;
  if (value === undefined) return { present: true };
  if (typeof value === "string") {
    const parsed = parseModelRef(value);
    return parsed ? { present: true, model: parsed } : { present: true, invalid: "continual-learning.json model must be provider/model" };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.keys(value as Record<string, unknown>).some((key) => key !== "provider" && key !== "model")) {
    return { present: true, invalid: "continual-learning.json model must be provider/model" };
  }
  const pair = validPair((value as Record<string, unknown>).provider, (value as Record<string, unknown>).model);
  if (!pair || (!pair.provider && !pair.model) || (pair.provider !== undefined) !== (pair.model !== undefined)) {
    return { present: true, invalid: "continual-learning.json model must be provider/model" };
  }
  return pair.provider && pair.model ? { present: true, model: pair } : { present: true };
}

export function writeMemoryConfig(config: MemoryConfig): void {
  const normalized = validPair(config.provider, config.model);
  if (!normalized || !normalized.provider || !normalized.model) {
    throw new Error("Memory model must include provider and model together.");
  }
  writeUnifiedConfig({ model: `${normalized.provider}/${normalized.model}` });
}

export function memoryConfigPath(): string {
  return unifiedConfigPath();
}

export function readDebugConfigState(): { enabled: boolean; invalid?: string } {
  try {
    const state = readUnifiedConfig();
    if (state.invalid) return { enabled: true, invalid: state.invalid };
    const value = state.record?.debug;
    if (value !== undefined && typeof value !== "boolean") {
      return { enabled: true, invalid: "debug must be a boolean" };
    }
    return { enabled: value !== false };
  } catch {
    return { enabled: true, invalid: "Debug configuration could not be read safely" };
  }
}

export type JevStage = "selection" | "memory" | "harness";
export interface JevLearningConfig {
  model: string;
  /** Grants semantic participation only, never file-write authority. */
  scopes: JevStage[];
  requestConcurrency?: number;
  /** Normal complete reviews request the service long context unless disabled. */
  longContext?: boolean;
  apiKey?: string;
}
export interface JevConfigState {
  config?: JevLearningConfig;
  invalid?: "invalid-config";
  disabled?: boolean;
}

/** User-level opt-in in the same file and safe boundaries. Reads only the Jev
 * section; unrelated unified configuration is preserved. */
export function readJevConfigState(): JevConfigState {
  try {
    const state = readUnifiedConfig();
    if (state.invalid) return { invalid: "invalid-config" };
    if (!state.record) return {};
    const jev = state.record.jev;
    if (jev === undefined) return {};
    if (jev === false) return { disabled: true };
    if (jev !== true && (!jev || typeof jev !== "object" || Array.isArray(jev))) return { invalid: "invalid-config" };
    const value = (jev === true ? {} : jev) as Record<string, unknown>;
    if (Object.keys(value).some(key => !["model", "scopes", "enabled", "requestConcurrency", "longContext", "apiKey"].includes(key))
      || (value.enabled !== undefined && typeof value.enabled !== "boolean")
      || (value.apiKey !== undefined && (typeof value.apiKey !== "string" || !value.apiKey.trim()))
      || (value.longContext !== undefined && typeof value.longContext !== "boolean")
      || (value.requestConcurrency !== undefined && (!Number.isSafeInteger(value.requestConcurrency) || Number(value.requestConcurrency) < 1 || Number(value.requestConcurrency) > 4))) return { invalid: "invalid-config" };
    const model = value.model ?? "jev-1.13.0";
    const scopes = value.scopes ?? ["selection", "memory", "harness"];
    if (typeof model !== "string" || !/^(?:jev-[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|jev-latest|jev-preview)$/.test(model)
      || !Array.isArray(scopes) || scopes.length < 1 || scopes.length > 3
      || !scopes.every(scope => ["selection", "memory", "harness"].includes(scope))
      || new Set(scopes).size !== scopes.length) return { invalid: "invalid-config" };
    if (value.enabled === false) return { disabled: true };
    return { config: { model, scopes: scopes as JevStage[],
      ...(typeof value.longContext === "boolean" ? {longContext: value.longContext} : {}),
      ...(typeof value.requestConcurrency === "number" ? {requestConcurrency: value.requestConcurrency} : {}),
      ...(typeof value.apiKey === "string" ? { apiKey: value.apiKey } : {}) } };
  } catch {
    return { invalid: "invalid-config" };
  }
}

/** Explicit capability opt-in for a verified learning-model gateway. */
function plannerOutputCapabilityEnabled(key: "plannerJsonOutput" | "plannerStructuredOutput"): boolean {
  try {
    const state = readUnifiedConfig();
    if (state.invalid || !state.record) return false;
    return state.record[key] === true;
  } catch { return false; }
}

export function plannerJsonOutputEnabled(): boolean {
  return plannerOutputCapabilityEnabled("plannerJsonOutput");
}

/** Separate opt-in: JSON syntax support does not establish schema support. */
export function plannerStructuredOutputEnabled(): boolean {
  return plannerOutputCapabilityEnabled("plannerStructuredOutput");
}

/** Generation-only operator choice. It does not change independent reviewers. */
export function plannerThinkingLevel(): string | undefined {
  try {
    const file = join(assertSafeAgentDir(false), "continual-learning.json");
    if (!lstatIfPresent(file)) return undefined;
    assertSafeConfigTarget(file);
    if (lstatSync(file).size > 4096) throw new Error("Learning planner configuration exceeds its bound");
    const raw: unknown = JSON.parse(readFileSync(file, "utf8"));
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Invalid learning planner configuration");
    const value = (raw as Record<string, unknown>).plannerThinkingLevel;
    if (value === undefined) return undefined;
    if (typeof value !== "string" || !["off", "minimal", "low", "medium", "high", "xhigh", "max"].includes(value)) {
      throw new Error("Invalid learning planner thinking level");
    }
    return value;
  } catch {
    throw new Error("Invalid learning planner configuration");
  }
}
