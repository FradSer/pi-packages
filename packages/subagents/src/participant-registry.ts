/**
 * The seam between a child-process roster and a task set of Tasks.
 *
 * **Neither package imports the other.** `@fradser/pi-subagents` owns processes
 * and knows nothing about Tasks; `@fradser/pi-tasks` owns Tasks and knows nothing
 * about processes. What they share is one declared contract — the participant
 * registry — published through `@fradser/pi-kit`, so agreement is by import
 * rather than by two packages spelling a symbol key and a set of field names
 * identically by convention.
 *
 * **The task store reads the registry, so the task store keeps its own policy.** A resource
 * conflict is the task set's primitive; this registry supplies the participants to
 * compare and nothing else. A process layer that computed resource conflicts
 * would own a rule the domain then has to agree with, which is the coupling in
 * its other direction.
 *
 * Read at use time rather than claimed at load time, so which package loads first
 * stops mattering.
 */

import {
  publishParticipantRegistry,
  type Participant,
  type ParticipantAssignment,
  type ParticipantRegistry,
} from "@fradser/pi-kit";
import { getAgent, livingAgents, updateAgent, type Agent } from "./roster.ts";

export type { Participant, ParticipantAssignment, ParticipantRegistry };

/** Project one roster entry into what a task set is allowed to see. */
function project(entry: Agent): Participant {
  return {
    name: entry.name,
    spawnId: entry.spawnId,
    status: entry.status,
    ...(entry.assignment ? { assignment: entry.assignment } : {}),
    ...(entry.currentTaskId ? { currentTaskId: entry.currentTaskId } : {}),
  };
}

/** This roster as a participant registry. The only place roster state crosses into
 *  another package. */
export function rosterAsParticipantRegistry(): ParticipantRegistry {
  return {
    get: (holder) => {
      const entry = getAgent(holder);
      return entry ? project(entry) : undefined;
    },
    list: () => livingAgents().map(project),
    sync: (holder, assignment, taskId) => {
      updateAgent(holder, {
        ...(assignment ? { assignment } : { assignment: undefined }),
        ...(taskId ? { currentTaskId: taskId } : { currentTaskId: undefined }),
      });
    },
    /**
     * Whether this participant can hold work now, and whether `incarnation` is
     * its current one. The task store cannot answer either: a stopped participant and
     * a replaced one are the same fact, and only the roster knows which.
     */
    current: (holder, incarnation) => {
      const entry = getAgent(holder);
      if (!entry || entry.status === "stopped") return false;
      return incarnation === undefined || entry.spawnId === incarnation;
    },
  };
}

/** Publish this roster to the installed task store. Idempotent: a
 *  reload republishes rather than stacking, and the roster it publishes is the same
 *  object the earlier publish used, because the roster map itself is shared. */
export function publishParticipantRegistryFromRoster(): void {
  publishParticipantRegistry(rosterAsParticipantRegistry());
}
