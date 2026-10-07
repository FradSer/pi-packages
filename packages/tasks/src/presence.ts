/**
 * The note that says when the task tools are worth reaching for.
 *
 * The tool descriptions already say what each tool is for, and they are sent on
 * every turn. What they cannot say is when the situation calls for one: a session
 * that never considers recording work never reads a description of the tool that
 * would record it. Measured over 1152 recorded sessions, `create_task` ran 17
 * times in 7 sessions while `bash` ran 78178 times, with the descriptions present
 * the whole time.
 *
 * So the package injects one bounded note per request. Three properties make that
 * affordable, and all three are deliberate:
 *
 * **The note is identical on every turn.** It carries no task state, so the same
 * text lands at the same index and request N+1 stays a true prefix of request N.
 * The provider's implicit prefix cache therefore keeps matching, and the cost is
 * one stable block rather than a fresh tail on every request.
 *
 * **The note is a system message.** An earlier version sent it through the
 * `context` hook, which never sees the prompt and tool system messages, so the
 * note could only be a user-role message placed ahead of the user's own request.
 * A model reading that reports it as the user's message rather than as harness
 * context, which is exactly what happened: in a recorded run the model answered
 * that the block was "in your own message" while the note was in its context. The
 * `context_with_system` hook receives the whole transcript, so the note lands as
 * a system message after the system prompt and reads as what it is.
 *
 * **The note says what a task is not.** Two packages that both track outstanding
 * work are otherwise indistinguishable to a model reading two similar notes, and
 * choosing between them is the one thing it has to get right.
 */

/**
 * The note, bounded and stable.
 *
 * It names no task and counts nothing, so a session with a thousand tasks sends
 * exactly the text a session with none sends.
 */
export const TASK_CAPABILITY_NOTE = [
  "[pi-tasks capability]",
  "Tasks are this session's durable list of work: what must be done, what it depends on, and what proves it done.",
  "Record one with create_task when a request has several steps or several files, or when the work outlives this turn. A single edit is not a task.",
  "A task is not a goal. A goal is one objective that keeps running until it is met; a task is one unit of work in a list you order, take, and finish.",
  "Move work with update_task: status=in_progress takes it, status=completed delivers it with its evidence. Read one with get_task, or the list with list_tasks.",
].join("\n");

/** The role the note is sent under. It is context the harness supplies, not a
 *  request from the user, and it must not be attributable to one. */
const NOTE_ROLE = "system";

/**
 * Insert the note into a request, at a fixed position.
 *
 * The position is directly after the leading system message: the same index on
 * every turn, holding the same text, so each request begins with exactly the
 * previous one. Appending instead would put the note where the newest turn goes,
 * and every request would then differ from the last at that index.
 *
 * The leading system message keeps index zero, which is the one placement the
 * `context_with_system` contract requires: the handler owns the transcript, and
 * the prompt stays where the provider expects it.
 */
export function injectTaskCapabilityNote<T>(messages: readonly T[]): T[] {
  const out = [...messages];
  const first = out[0] as { role?: unknown } | undefined;
  const index = first && typeof first === "object" && first.role === "system" ? 1 : 0;
  // The one cast in this module, and it is the boundary itself: the note is a
  // message the harness will accept, and this package does not import the message
  // type it belongs to, because the type belongs to the host.
  out.splice(index, 0, { role: NOTE_ROLE, content: TASK_CAPABILITY_NOTE } as T);
  return out;
}
