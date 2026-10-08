/**
 * The Pi extension body for `@fradser/pi-tasks`.
 *
 * Lives in `src/` so `index.ts` can re-export it as the package's default export,
 * which is what lets one file serve as both the library entry and the extension
 * entry. A separate top-level extension file would split that, and the root
 * `index.ts` is what every other runtime package here loads.
 *
 * It registers the four task tools, the note that makes them discoverable, and
 * owns nothing else. Tasks changes are announced
 * through `pi.events` so a coordinator can notice and wake participants without this
 * package knowing what a participant is; with nobody subscribed the emit is a
 * no-op, which is the correct degradation.
 *
 * It is also where a standalone install gets durability. The tasks file is
 * written here rather than only by a layer that claims the store, so installing
 * this package alone gives a task set that survives a restart. A claim takes the
 * duty over with it — `isTaskStoreClaimed` is true once it has — and this
 * handler stands down, so exactly one writer is ever active.
 *
 * `session_start` fires again for a session switch, and the writer it attached
 * belongs to the session it was attached for. Releasing it first is what keeps
 * every path below honest: whatever this process writes after a switch belongs to
 * the session that is open, or to nothing at all.
 */

import {
  readTasksFile,
  tasksFilePath,
  writeTasksFile,
} from "./persist.ts";
import { createTaskResultRenderer, createTaskStatusRenderer } from "./rows.ts";
import { registerTaskStopCheck, taskStatusSpec } from "./stop-check.ts";
import {
  clearTasks,
  isTaskStoreClaimed,
  loadTasks,
  onTasksChanged,
  setStoreNotice,
  tasks,
} from "./store.ts";
import { injectTaskCapabilityNote } from "./presence.ts";
import { registerTaskTools } from "./tool.ts";

export default function piTasks(pi: Parameters<typeof registerTaskTools>[0]): void {
  registerTaskTools(pi, { renderResult: createTaskResultRenderer });

  // Two surfaces carry the trigger conditions, and they do different jobs. The
  // tool descriptions say what each tool is for, beside the tool itself. The note
  // says when the situation calls for one at all, which a description cannot say:
  // a session that never considers recording work never reads a description of
  // the tool that would record it. The note is bounded, carries no task state, and
  // lands at a fixed index, so it costs one stable block per request and keeps
  // each request a prefix of the last. The settle reminder is the third surface,
  // and it fires only when unfinished tasks already exist.
  //
  // `context_with_system` rather than `context`: the plain hook never sees the
  // prompt and tool system messages, so the note could only be a user-role message
  // ahead of the user's own request, and a model reading that reports it as the
  // user's message instead of harness context. This hook receives the whole
  // transcript, and it runs after every `context` handler, so the goal note is
  // already in the list and is left untouched.
  pi.on("context_with_system", async (event) => ({ messages: injectTaskCapabilityNote(event.messages) }));
  pi.on("session_start", async (_event, ctx) => {
    // Released before anything else, so every path below starts with this process
    // owning no task file at all. A writer surviving a switch is not a second
    // writer on one file; it is the only writer, on the wrong file.
    onTasksChanged(undefined);
    // A notice from the session that was left is not news about this one.
    setStoreNotice(undefined);
    if (isTaskStoreClaimed()) {
      // A layer claimed the store outright, and claiming it includes owning the
      // durable file. Standing down here is what keeps the file single-writer.
      //
      // Not `isCoordinated()`: that also answers true when a participant registry
      // was published beside the store, and nobody is writing the file in that
      // case. Standing down there left tasks recorded in memory and nothing on
      // disk, for every install of this package beside a registry publisher that
      // did not also install a layer that claims the store.
      //
      // Nothing is cleared on this path either. The claimer loaded the tasks
      // itself and owns them; clearing here would empty the very set it just
      // restored, and the next snapshot it writes would persist that emptiness
      // over durable work.
      pi.events.emit("pi-tasks:ready", {});
      return;
    }
    // The tasks in memory belong to the session that was left, so they go before
    // the new ones are read in. Unconditional rather than guarded on a session
    // file: the file below is the source of truth either way, and a surviving
    // Task is one the file no longer holds.
    clearTasks();
    const writeTo = ctx ? tasksFilePath(ctx.sessionManager?.getSessionFile(), ctx.cwd) : undefined;
    if (writeTo) {
      try {
        const persisted = readTasksFile(writeTo);
        if (persisted) loadTasks(persisted.tasks);
      } catch (error) {
        // A present-but-unreadable file is reported rather than treated as empty,
        // and this process does not become a writer for a file it could not read:
        // overwriting it would discard the very work it failed to load.
        const notice = error instanceof Error ? error.message : String(error);
        setStoreNotice(notice);
        pi.events.emit("pi-tasks:ready", {});
        return;
      }
      onTasksChanged(() => {
        try {
          writeTasksFile(writeTo, tasks);
          setStoreNotice(undefined);
        } catch (error) {
          setStoreNotice(`The durable task file at ${writeTo} could not be written: ${error instanceof Error ? error.message : String(error)}`);
        }
      });
    }
    pi.events.emit("pi-tasks:ready", {});
  });

  registerTaskStopCheck(pi, createTaskStatusRenderer(taskStatusSpec));
}
