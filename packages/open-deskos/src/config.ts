import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { type DeskLinkConfig } from "./types.ts";

/** A reporting machine identity stable across restarts of the same machine. */
export function defaultMachineName(hostname = os.hostname()): string {
  const trimmed = hostname.replace(/\.local$/i, "").trim();
  return trimmed.length > 0 ? trimmed : "pi-machine";
}

function readPort(raw: string): number | null {
  const port = Number.parseInt(raw, 10);
  return Number.isInteger(port) && port > 0 && port <= 65535 ? port : null;
}

/**
 * Read the Desk Link configuration. An unconfigured machine reports nothing:
 * a missing address or token is silent, never a partially configured link.
 */
export function readDeskLinkConfig(env: NodeJS.ProcessEnv = process.env): DeskLinkConfig | null {
  const address = (env.ODK_DESK_LINK_ADDRESS ?? "").trim();
  const token = (env.ODK_DESK_LINK_TOKEN ?? "").trim();
  if (address.length === 0 || token.length === 0) return null;
  const separator = address.lastIndexOf(":");
  if (separator <= 0) return null;
  const host = address.slice(0, separator).trim();
  const port = readPort(address.slice(separator + 1).trim());
  if (host.length === 0 || port === null) return null;
  const controlToken = (env.ODK_DESK_LINK_CONTROL_TOKEN ?? "").trim();
  return {
    machine: (env.ODK_DESK_LINK_MACHINE ?? "").trim() || defaultMachineName(),
    host,
    port,
    token,
    ...(controlToken.length > 0 ? { controlToken } : {}),
  };
}

/** Never log a token: identify a link by a short digest instead. */
export function tokenDigest(token: string): string {
  return createHash("sha256").update(token).digest("hex").slice(0, 8);
}

/** Where a machine that reports to more than one desk states them. */
export const DEFAULT_DESKS_FILE = path.join(os.homedir(), ".config", "open-deskos", "desks.json");

export interface DeskLinkConfigSet {
  configs: DeskLinkConfig[];
  /** Entries a desks file stated that this machine will not use, with the reason. */
  refusals: string[];
  source: "desks-file" | "environment" | "none";
}

function readPortOrNull(raw: string): number | null {
  return readPort(raw);
}

/** One entry of a desks file, or the reason it is not usable. */
function configFromEntry(entry: unknown, machine: string): DeskLinkConfig | string {
  if (entry === null || typeof entry !== "object") return "an entry is not an object";
  const record = entry as Record<string, unknown>;
  const address = typeof record.address === "string" ? record.address.trim() : "";
  const token = typeof record.token === "string" ? record.token.trim() : "";
  if (address.length === 0) return "an entry states no address";
  if (token.length === 0) return `the entry for ${address} states no token`;
  const separator = address.lastIndexOf(":");
  const host = separator > 0 ? address.slice(0, separator).trim() : "";
  const port = separator > 0 ? readPortOrNull(address.slice(separator + 1).trim()) : null;
  if (host.length === 0 || port === null) return `${address} is not host:port`;
  const controlToken = typeof record.controlToken === "string" ? record.controlToken.trim() : "";
  const entryMachine = typeof record.machine === "string" && record.machine.trim().length > 0 ? record.machine.trim() : machine;
  return {
    machine: entryMachine,
    host,
    port,
    token,
    ...(controlToken.length > 0 ? { controlToken } : {}),
  };
}

function entriesFrom(text: string): unknown[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (Array.isArray(parsed)) return parsed;
  const stated = (parsed as { desks?: unknown } | null)?.desks;
  return Array.isArray(stated) ? stated : null;
}

/**
 * Every desk this machine reports to.
 *
 * One disk file is the source of truth when there is one, because a machine that
 * reports to several desks needs a token per desk and an environment variable
 * cannot state that unambiguously. The single-desk environment form keeps
 * working for a machine that reports to one. An operator who names a file and
 * then has it not used is told, because silence there would look like a link
 * that simply never connects.
 */
export function readDeskLinkConfigs(
  env: NodeJS.ProcessEnv = process.env,
  options: { readFile?: (file: string) => string } = {},
): DeskLinkConfigSet {
  const readFile = options.readFile ?? ((file: string) => readFileSync(file, "utf8"));
  const explicit = (env.ODK_DESK_LINK_DESKS_FILE ?? "").trim();
  const machine = (env.ODK_DESK_LINK_MACHINE ?? "").trim() || defaultMachineName();
  const file = explicit.length > 0 ? explicit : DEFAULT_DESKS_FILE;
  const refusals: string[] = [];

  let text: string | null = null;
  try {
    text = readFile(file);
  } catch (error) {
    const code = (error as { code?: string } | null)?.code;
    if (code !== "ENOENT" || explicit.length > 0) {
      refusals.push(`refusing ${file}: it could not be read${code === undefined ? "" : ` (${code})`}`);
      return { configs: [], refusals, source: "desks-file" };
    }
  }

  if (text !== null) {
    const entries = entriesFrom(text);
    if (entries === null) {
      refusals.push(`refusing ${file}: it states no list of desks`);
      return { configs: [], refusals, source: "desks-file" };
    }
    const configs: DeskLinkConfig[] = [];
    const seen = new Set<string>();
    for (const entry of entries) {
      const result = configFromEntry(entry, machine);
      if (typeof result === "string") {
        refusals.push(`refusing ${file}: ${result}`);
        continue;
      }
      const endpoint = `${result.host}:${result.port}`;
      if (seen.has(endpoint)) {
        refusals.push(`${endpoint} is listed more than once in ${file}; the first entry is used`);
        continue;
      }
      seen.add(endpoint);
      configs.push(result);
    }
    return { configs, refusals, source: "desks-file" };
  }

  const single = readDeskLinkConfig(env);
  return single === null
    ? { configs: [], refusals, source: "none" }
    : { configs: [single], refusals, source: "environment" };
}
