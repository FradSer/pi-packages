/** Pure input validation for the flat child-execution boundary.
 * Definition discovery, tool grants and exact-incarnation lookup belong to the
 * handler. Validating an input never creates an identity or starts a child.
 * The boundary mirrors the four intent tools, so `agent_input` arrives as one
 * operation with its delivery rather than as two verbs.
 */

export type AgentInput =
  | {
    operation: "start";
    name?: string;
    prompt?: string;
    description?: string;
    role_prompt?: string;
    tools?: string[];
    model?: string;
    fork?: boolean;
  }
  | { operation: "input"; session: string; prompt: string; delivery: "next" | "steer" }
  | { operation: "list"; offset: number; limit: number }
  | { operation: "stop"; session: string };

const OPERATIONS = ["start", "input", "list", "stop"] as const;
const OPERATION_FIELDS: Record<AgentInput["operation"], readonly string[]> = {
  start: ["operation", "name", "prompt", "description", "role_prompt", "tools", "model", "fork"],
  input: ["operation", "session", "prompt", "delivery"],
  list: ["operation", "offset", "limit"],
  stop: ["operation", "session"],
};
const KNOWN_FIELDS = new Set(Object.values(OPERATION_FIELDS).flat());
const NAME_PATTERN = /^[A-Za-z][A-Za-z0-9._-]{0,63}$/;
const SESSION_PATTERN = /^session:([A-Za-z][A-Za-z0-9._-]{0,63}):([^:\s]+)$/;
const SESSION_GUIDANCE = "Use session:<name>:<incarnation>, copied in full from start or list, including the session: prefix.";

function isParameterObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOperation(value: unknown): value is AgentInput["operation"] {
  return typeof value === "string" && OPERATIONS.some(operation => operation === value);
}

function fail(error: string): { ok: false; error: string } {
  return { ok: false, error };
}

/** Only absent options receive defaults. Present values are checked without
 * coercion, and authored text stays verbatim after a whitespace-only check.
 */
export function validateAgentInput(params: unknown):
  | { ok: true; value: AgentInput }
  | { ok: false; error: string } {
  if (!isParameterObject(params)) return fail("Agent input must be a non-null object, not an array or primitive.");

  const operation = Object.hasOwn(params, "operation") ? params.operation : "start";
  if (!isOperation(operation)) {
    return fail(`Invalid agent operation. Use ${OPERATIONS.join(", ")}. Only an omitted operation defaults to start.`);
  }

  const allowed = OPERATION_FIELDS[operation];
  for (const field of Reflect.ownKeys(params)) {
    if (typeof field !== "string" || !KNOWN_FIELDS.has(field)) {
      return fail(`Unknown agent parameter "${String(field)}". Operation "${operation}" takes: ${allowed.join(", ")}.`);
    }
    if (!allowed.includes(field)) {
      return fail(`Parameter "${field}" is not allowed for operation "${operation}". This operation takes: ${allowed.join(", ")}.`
        + (allowed.includes("session") ? ` ${SESSION_GUIDANCE}` : ""));
    }
  }

  if (operation === "start") {
    const value: Extract<AgentInput, { operation: "start" }> = { operation };
    for (const field of ["name", "prompt", "description", "role_prompt", "model"] as const) {
      if (!Object.hasOwn(params, field)) continue;
      const text = params[field];
      if (typeof text !== "string" || !text.trim()) {
        return fail(`Parameter "${field}" must be a nonempty string; omit it when not needed.`);
      }
      if (field === "name" && !NAME_PATTERN.test(text.trim())) {
        return fail('Parameter "name" must start with a letter and contain at most 64 letters, digits, dots, dashes or underscores.');
      }
      if (field === "model" && /[\r\n]/.test(text)) {
        return fail('Parameter "model" must be a single-line provider/model reference.');
      }
      value[field] = field === "name" || field === "model" ? text.trim() : text;
    }

    if (Object.hasOwn(params, "tools")) {
      const entries: unknown = params.tools;
      if (!Array.isArray(entries)) return fail('Parameter "tools" must be an array of nonempty strings.');
      const tools: string[] = [];
      for (let index = 0; index < entries.length; index++) {
        const entry: unknown = entries[index];
        if (typeof entry !== "string" || !entry.trim()) {
          return fail(`Parameter "tools" item ${index} must be a nonempty string; no items are silently filtered.`);
        }
        tools.push(entry.trim());
      }
      // Keep an explicit [] and duplicates. The handler checks the role ceiling
      // and built-in/capability vocabulary; shape validation grants no tool.
      value.tools = tools;
    }

    if (Object.hasOwn(params, "fork")) {
      if (typeof params.fork !== "boolean") return fail('Parameter "fork" must be a boolean.');
      value.fork = params.fork;
    }
    if (!value.prompt && !value.name) return fail('Starting an agent requires a nonempty "prompt" or "name".');
    return { ok: true, value };
  }

  if (operation === "list") {
    const offset = Object.hasOwn(params, "offset") ? params.offset : 0;
    const limit = Object.hasOwn(params, "limit") ? params.limit : 20;
    if (typeof offset !== "number" || !Number.isSafeInteger(offset) || offset < 0) {
      return fail('Parameter "offset" must be a safe integer at least 0.');
    }
    if (typeof limit !== "number" || !Number.isInteger(limit) || limit < 1 || limit > 50) {
      return fail('Parameter "limit" must be an integer from 1 through 50.');
    }
    return { ok: true, value: { operation, offset, limit } };
  }

  const rawSession = Object.hasOwn(params, "session") ? params.session : undefined;
  const session = typeof rawSession === "string" ? rawSession.trim() : undefined;
  if (!session || !SESSION_PATTERN.test(session)) {
    return fail((Object.hasOwn(params, "session")
      ? 'Invalid session handle. Parameter "session" must be a complete exact session handle. '
      : 'Parameter "session" requires a complete exact session handle. ') + SESSION_GUIDANCE);
  }

  if (operation === "input") {
    const prompt = Object.hasOwn(params, "prompt") ? params.prompt : undefined;
    if (typeof prompt !== "string" || !prompt.trim()) {
      return fail(`Operation "input" requires a nonempty "prompt" and its exact session handle. ${SESSION_GUIDANCE}`);
    }
    const delivery = Object.hasOwn(params, "delivery") ? params.delivery : undefined;
    if (delivery !== "next" && delivery !== "steer") {
      return fail('Parameter "delivery" must be "next" or "steer". A steer guides the turn in flight; a next input waits for it.');
    }
    return { ok: true, value: { operation, session, prompt, delivery } };
  }

  return { ok: true, value: { operation, session } };
}
