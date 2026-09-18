import { createHash } from "node:crypto";
import os from "node:os";
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
  return {
    machine: (env.ODK_DESK_LINK_MACHINE ?? "").trim() || defaultMachineName(),
    host,
    port,
    token,
  };
}

/** Never log a token: identify a link by a short digest instead. */
export function tokenDigest(token: string): string {
  return createHash("sha256").update(token).digest("hex").slice(0, 8);
}
