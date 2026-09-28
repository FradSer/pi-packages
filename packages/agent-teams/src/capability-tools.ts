/**
 * The coordination capability set this package contributes to a spawned child,
 * and the worker extension entry that registers it.
 *
 * These live in their own dependency-free module rather than beside the
 * registrations in `worker.ts` because two consumers need them and one of them
 * is imported by `worker.ts`: `tool-copy.ts` renders the effective grant, and
 * `team-machine.ts` passes both to the spawner. Declaring them in `worker.ts`
 * would make `tool-copy.ts` import it and close a cycle.
 *
 * The spawner hardcodes none of this. A consumer that loads only its own worker
 * extension advertises only what it implements, which is what keeps
 * `@fradser/pi-subagents` from granting `work` and `agent_event` when it is
 * installed without this package.
 */

import * as path from "node:path";
import { fileURLToPath } from "node:url";

/** Tool ids registered by this package's worker extension inside a child.
 *  Kept in sync with the `registerTool` calls in `worker.ts`. */
export const WORKER_CAPABILITY_TOOLS: readonly string[] = [
  "agent_event",
  "work",
];

/** This package's worker extension entry, passed to a spawned child with `-e`.
 *  `--no-extensions` disables discovered extensions but still loads explicit
 *  paths. `src/index.ts` is the extension module; the package-root `index.ts`
 *  only re-exports it. */
export const WORKER_EXTENSION_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "index.ts",
);
