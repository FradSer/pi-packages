/**
 * Session routes: the stable handle a caller uses to name one incarnation.
 *
 * Lives here because the roster moved here. A handle has to be minted where the
 * roster lives and understood by whoever spawns, and a route format split across
 * two packages is a route format that will drift.
 *
 * The bare `session:<name>` form is deliberately weaker than the exact form and is
 * accepted only where a caller has no other choice. Naming an incarnation matters:
 * a name can be reused by a replacement resident, and a replacement must not be
 * reachable through its predecessor's handle.
 */

import type { Teammate } from "./roster.ts";

/** `session:<name>` — the name, bound to whichever incarnation is living now. */
export function sessionRoute(name: string): string {
  return `session:${name}`;
}

/** `session:<name>:<spawnId>` — one incarnation, permanently. */
export function exactSessionRoute(name: string, spawnId: string): string {
  return `session:${name}:${spawnId}`;
}

export function parseExactSessionRoute(route: string): { name: string; spawnId: string } | undefined {
  const match = /^session:([^:]+):([^:]+)$/.exec(route);
  return match ? { name: match[1], spawnId: match[2] } : undefined;
}

/** Resolve an exact route against a living roster, or undefined when that
 *  incarnation is gone. A retired handle never resolves to its replacement. */
export function resolveExactSession(
  route: string,
  roster: readonly Teammate[],
): Teammate | undefined {
  const parsed = parseExactSessionRoute(route);
  if (!parsed) return undefined;
  return roster.find(
    (teammate) => teammate.name === parsed.name
      && teammate.spawnId === parsed.spawnId
      && teammate.status !== "stopped",
  );
}
