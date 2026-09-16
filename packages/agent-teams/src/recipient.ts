import type { Teammate } from "./types.ts";

export function sessionRoute(name: string): string {
  return `session:${name}`;
}

export function exactSessionRoute(name: string, spawnId: string): string {
  return `session:${name}:${spawnId}`;
}

export function parseExactSessionRoute(route: string): { name: string; spawnId: string } | undefined {
  const match = /^session:([^:]+):([^:]+)$/.exec(route);
  return match ? { name: match[1], spawnId: match[2] } : undefined;
}

export function resolveExactSession(route: string, roster: readonly Teammate[]): Teammate | undefined {
  const parsed = parseExactSessionRoute(route);
  if (!parsed) return undefined;
  return roster.find((teammate) => teammate.name === parsed.name && teammate.spawnId === parsed.spawnId && teammate.status !== "stopped");
}

export function resolveRecipient(
  to: string,
  roster: ReadonlyArray<{ name: string; agent: string; status: string; spawnId?: string }>,
): string {
  const exact = parseExactSessionRoute(to);
  if (exact) {
    const matched = roster.find((entry) => entry.name === exact.name && entry.spawnId === exact.spawnId && entry.status !== "stopped");
    if (matched) return matched.name;
    throw new Error(`No living session named "${to}".`);
  }
  const explicit = to.startsWith("session:");
  const name = explicit ? to.slice("session:".length) : to;
  const living = roster.filter((entry) => entry.status !== "stopped");
  const recipients = living.filter((entry) => entry.name === name || (!explicit && entry.agent === to));
  if (recipients.length > 1) {
    throw new Error(`Ambiguous Agent @${to}. Use a precise route: ${recipients.map((entry) => entry.spawnId ? exactSessionRoute(entry.name, entry.spawnId) : sessionRoute(entry.name)).join(", ")}.`);
  }
  if (recipients.length === 1) return recipients[0].name;
  throw new Error(`No living teammate named "${to}".`);
}
