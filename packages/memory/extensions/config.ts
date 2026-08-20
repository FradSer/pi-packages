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
  const stat = lstatIfPresent(absolute);
  if (stat?.isSymbolicLink()) throw new Error(`Memory config path is symlinked: ${absolute}`);
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
  const file = configPath();
  try {
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

export function readMemoryConfig(): MemoryConfig {
  return readMemoryConfigState().config;
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
