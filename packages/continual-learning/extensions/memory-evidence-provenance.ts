type RecordValue = Record<string, unknown>;
function record(value: unknown): RecordValue | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : undefined;
}
function message(entry: unknown): RecordValue | undefined {
  return record(record(entry)?.message) ?? record(entry);
}

const LOCAL_TOOLS = new Set(["read", "learning_read", "bash", "exec", "exec_command", "codemode", "functions.exec", "edit", "write"]);
// The escaped project scope also recognizes isolated/custom agent directories.
// A source filename such as memory-reader.ts is not a managed Memory surface.
const MEMORY_SURFACE = /(?:^|[\\/\s"'`])\.memory(?=[\\/\s"'`]|$)|(?:^|[\\/\s"'`])\.pi[\\/]+agent[\\/]+memory(?=[\\/\s"'`]|$)|(?:^|[\\/\s"'`])memory[\\/]+--[^\\/"'`]+--(?=[\\/\s"'`]|$)/i;

function touchesMemory(value: unknown): boolean {
  if (typeof value === "string") return MEMORY_SURFACE.test(value);
  if (Array.isArray(value)) return value.some(touchesMemory);
  const fields = record(value);
  return fields !== undefined && Object.values(fields).some(touchesMemory);
}

/** A local invocation touching managed Memory may return a readback or a mixed
 * aggregate. Without separate nested-source provenance, no part of that result
 * independently establishes project facts. Keep its complete text as context.
 * This conservative classification grants no authority and does not attempt to
 * execute/interpret shell or JavaScript. Unknown invocations still require the
 * ordinary complete semantic review; absence of this flag is not source proof. */
export function memoryReferenceResults(entries: readonly unknown[]): ReadonlySet<number> {
  const invocations = new Set<string>();
  const results = new Set<number>();
  entries.forEach((entry, index) => {
    const row = message(entry);
    if (row?.role === "assistant" && Array.isArray(row.content)) {
      for (const value of row.content) {
        const call = record(value);
        if (call?.type !== "toolCall" || typeof call.id !== "string"
          || typeof call.name !== "string" || !LOCAL_TOOLS.has(call.name)) continue;
        // Frozen invocation arguments, never candidate-provided provenance or
        // path names merely mentioned in tool-output prose.
        const args = record(call.arguments);
        const input = ["read", "learning_read", "edit", "write"].includes(call.name)
          ? args?.path ?? args?.file_path : call.arguments;
        if (touchesMemory(input)) {
          invocations.add(`${call.name}\0${call.id}`);
        }
      }
    }
    if (row?.role === "toolResult" && row.isError !== true && typeof row.toolCallId === "string"
      && typeof row.toolName === "string" && invocations.has(`${row.toolName}\0${row.toolCallId}`)) results.add(index);
  });
  return results;
}
