/**
 * Pure Work Item graph and resource rules.
 *
 * Every function here is total over its arguments and touches no state, so the
 * dependency graph and resource-conflict semantics have exactly one
 * implementation across the leader, the worker, and any consumer that only wants
 * the rules. `resourcesConflict` is the primitive; deciding *which* held
 * assignments to compare against it is a roster question and stays with the
 * package that owns the roster.
 */

import type { BoardTask } from "./types.ts";

/** Longest derived Work id. Long enough to stay readable in a board row, short
 * enough to stay a safe filename segment. */
export const MAX_TASK_ID_LENGTH = 48;

/** A readable, filesystem-safe id derived from the subject:
 *  "Polish login flow" -> "polish-login-flow"; duplicates get -2, -3, ... */
export function taskIdFromSubject(subject: string, taken: ReadonlySet<string>): string {
  const base = subject
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_TASK_ID_LENGTH)
    .replace(/-+$/g, "") || "task";
  let id = base;
  for (let n = 2; taken.has(id); n++) {
    const suffix = `-${n}`;
    id = base.slice(0, Math.max(1, MAX_TASK_ID_LENGTH - suffix.length)).replace(/-+$/g, "") + suffix;
  }
  return id;
}

/** Trim, drop empties, de-duplicate, and order resource tags so two callers
 * describing the same lease cannot disagree through ordering alone. */
export function normalizeResources(resources: readonly string[] | undefined): string[] {
  return [...new Set((resources ?? [])
    .map((resource) => resource.trim().replace(/^\/+|\/+$/g, ""))
    .filter(Boolean))]
    .sort();
}

/** Follow an obsolete dependency to its latest replacement. An invalid persisted
 * chain is rejected rather than silently making a future Work Item unclaimable. */
export function canonicalDependency(taskId: string, tasks: Record<string, BoardTask>): string | undefined {
  const seen = new Set<string>();
  let current = taskId;
  while (true) {
    if (seen.has(current)) return undefined;
    seen.add(current);
    const task = tasks[current];
    if (!task) return undefined;
    if (task.status !== "superseded") return current;
    if (!task.supersededBy) return undefined;
    current = task.supersededBy;
  }
}

/** Resolve every dependency to its canonical target, or undefined when any link
 * in any chain is broken or cyclic. */
export function canonicalDependencies(
  dependencies: readonly string[],
  tasks: Record<string, BoardTask>,
): string[] | undefined {
  const canonical: string[] = [];
  for (const dependency of dependencies) {
    const resolved = canonicalDependency(dependency, tasks);
    if (!resolved) return undefined;
    if (!canonical.includes(resolved)) canonical.push(resolved);
  }
  return canonical;
}

/** Depth-first cycle detection over a dependency graph. A cycle would make every
 * Work Item in it permanently unclaimable, so it is refused at creation. */
export function hasDependencyCycle(graph: Map<string, readonly string[]>): boolean {
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const visit = (taskId: string): boolean => {
    if (visiting.has(taskId)) return true;
    if (visited.has(taskId)) return false;
    visiting.add(taskId);
    for (const dependency of graph.get(taskId) ?? []) {
      if (graph.has(dependency) && visit(dependency)) return true;
    }
    visiting.delete(taskId);
    visited.add(taskId);
    return false;
  };
  return [...graph.keys()].some(visit);
}

/** `firmware/sub-node` conflicts with itself and descendants such as
 * `firmware/sub-node/app`; unrelated siblings stay concurrently claimable. */
export function resourcesConflict(left: readonly string[], right: readonly string[]): boolean {
  return left.some((a) => right.some((b) => a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`)));
}
