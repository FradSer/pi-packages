/**
 * Pure Task graph and resource rules.
 *
 * Every function here is total over its arguments and touches no state, so the
 * dependency graph and resource-conflict semantics have exactly one
 * implementation across every consumer that only wants the rules.
 * `resourcesConflict` is the primitive; deciding *which* held assignments to
 * compare against it is a participant question and stays with whoever owns the
 * participant registry.
 */

import type { Task } from "./types.ts";

/** Longest derived Task id. Long enough to stay readable in a task set row, short
 * enough to stay a safe filename segment. */
export const MAX_TASK_ID_LENGTH = 48;

/** Cut a slug at its last word boundary within `limit`, so a derived id never ends
 *  inside a word. A single word longer than the limit is the one case that has to
 *  cut at the limit, because no earlier boundary exists. */
function truncateAtWord(slug: string, limit: number): string {
  if (slug.length <= limit) return slug;
  const boundary = slug.slice(0, limit + 1).lastIndexOf("-");
  const cut = boundary > 0 ? slug.slice(0, boundary) : slug.slice(0, limit);
  return cut.replace(/-+$/g, "") || slug.slice(0, limit);
}

/** A readable, filesystem-safe id derived from the subject:
 *  "Polish login flow" -> "polish-login-flow"; a taken id gets -1, -2, ...
 *
 *  The id is minted once from the subject and stays the handle for the record.
 *  `update_task` keeps it across a rename, so `slug-1` names where the work
 *  entered the set rather than restating its current subject. */
export function taskIdFromSubject(subject: string, taken: ReadonlySet<string>): string {
  const slug = subject
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "") || "task";
  const base = truncateAtWord(slug, MAX_TASK_ID_LENGTH) || "task";
  let id = base;
  for (let n = 1; taken.has(id); n++) {
    const suffix = `-${n}`;
    id = `${truncateAtWord(base, Math.max(1, MAX_TASK_ID_LENGTH - suffix.length))}${suffix}`;
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
 * chain is rejected rather than silently making a future Task untakeable. */
export function canonicalDependency(taskId: string, tasks: Record<string, Task>): string | undefined {
  const seen = new Set<string>();
  let current = taskId;
  while (true) {
    if (seen.has(current)) return undefined;
    seen.add(current);
    const task = tasks[current];
    if (!task) return undefined;
    if (task.replacementUnresolved) return undefined;
    if (!task.supersededBy) return current;
    current = task.supersededBy;
  }
}

/** Resolve every dependency to its canonical target, or undefined when any link
 * in any chain is broken or cyclic. */
export function canonicalDependencies(
  dependencies: readonly string[],
  tasks: Record<string, Task>,
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
 * Task in it permanently untakeable, so it is refused at creation. */
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
