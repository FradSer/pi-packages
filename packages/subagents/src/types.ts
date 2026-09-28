/**
 * Types owned by the subagent execution layer.
 *
 * Coordination vocabulary — Work Items, assignments, mailboxes, presence — stays
 * with the packages that own those concepts. This module holds only what
 * describing a spawned child requires, so the execution layer can be consumed
 * without importing any coordination state.
 */

/** Token and cost usage reported by a spawned child, accumulated across the
 * wake-up sequences of one incarnation. */
export interface WorkerUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}
