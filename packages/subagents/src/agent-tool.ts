/**
 * The `agent` tool: child process lifecycle, and nothing else.
 *
 * Four actions. `start` spawns, optionally with a prompt; `inspect` and `stop`
 * address one incarnation by its exact handle; `list` enumerates. There is no
 * action that records work, and none that talks to a peer — a task belongs to
 * `@fradser/pi-tasks` and a conversation to `@fradser/pi-agent-teams`.
 *
 * **Why `delegate` and `start` are one action.** They were the same operation
 * dispatched twice, and the only difference was whether a prompt was delivered.
 * Two names for one operation means the model has to decide which of two
 * identically-shaped spawn paths it meant, and the wrong one is invisible. One
 * action with an optional `prompt` makes the choice explicit and local: either
 * there is something to hand over now, or there is not.
 *
 * **Spawning does not create a task.** A prompted child's result arrives in the
 * caller's transcript. Anything that needs a record — dependencies, a completion
 * gate, a resource lease, survival across attempts — is a `task` the caller
 * creates, and a participant takes it. That is why no action here accepts a
 * verify gate, a resource list, or a subject: there is no task to attach them to.
 *
 * **The coordinator is optional.** A richer host (board notices, assignment
 * authority, a fresh session per assignment) publishes itself through
 * `setAgentHost` when a team runtime is loaded. Without one, this tool falls back
 * to the raw spawner, which is what makes `@fradser/pi-subagents` installable and
 * usable on its own.
 */

import { randomUUID } from "node:crypto";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerSessionAgent, resolveAgent } from "./agents.ts";
import { configureBoardStoreIfUnset, resourcesConflict, type WorkAssignment } from "@fradser/pi-tasks";
import { WORKER_BUILTIN_TOOLS } from "./worker-tools.ts";
import { getTeammate, listTeammates, livingTeammates, registerTeammate, updateTeammate, updateTeammateProgress, type Teammate } from "./roster.ts";
import { emptyToolCall, type createStaticToolLifecycleResultRenderer } from "@fradser/pi-kit";
import { exactSessionRoute, parseExactSessionRoute, resolveExactSession } from "./session-route.ts";
import { type SessionEndedNotice, type SessionNoticeSender, type SessionResultNotice } from "./session-result.ts";
import { spawnResident, terminateTeammate } from "./spawner.ts";
import { snapshotWorkContext } from "./work-context.ts";

/** Tool ids this extension registers. Declared so a spawner can grant it without
 *  hardcoding a name. */
export const AGENT_CAPABILITY_TOOLS: readonly string[] = ["agent"];

/** What a caller may ask for when starting an agent. */
export interface AgentStartRequest {
  name: string;
  /** Deliver this immediately. Omit to leave the agent idle. */
  prompt?: string;
  /** Inline role for a name that has no persisted definition. */
  definition?: { description: string; prompt: string; tools?: string[]; model?: string };
  model?: string;
  tools?: string[];
  /** Seed the child with a snapshot of the caller's active context. */
  fork?: boolean;
}

/** A richer spawn/close path published by a team runtime.
 *
 * `start` may return a promise, and this tool awaits it. That is deliberate: a
 * team spawn has to prove the child is actually up before it reports a handle,
 * because "started" is the caller's only evidence that anything exists. The host
 * owns whatever waiting that requires — an RPC readiness probe, a session reset,
 * a worktree provision — and this tool owns none of it, which is why the
 * standalone path can return immediately and still be honest about it. */
export interface AgentHost {
  start(request: AgentStartRequest):
  | { ok: true; session: string }
  | { ok: false; error: string }
  | Promise<{ ok: true; session: string } | { ok: false; error: string }>;
  stop(name: string, spawnId: string): Promise<{ ok: true; body?: string } | { ok: false; error: string }>;
}

/**
 * Where a published host is kept.
 *
 * On `globalThis` under a `Symbol.for` key, deliberately, and not in a module
 * variable. Pi loads each installed package with its own module root, so a team
 * runtime that imports `@fradser/pi-subagents` and the very same extension entry Pi
 * loaded through a `node_modules` path can end up with two module instances — and
 * a module-level variable set by one is invisible to the other. That is not
 * hypothetical here: it is exactly how a published host went missing, leaving
 * every spawn on the standalone path and every child's output discarded.
 *
 * `Symbol.for` rather than a plain string so two copies of this module still agree
 * on the key, and `globalThis` so they agree on the slot.
 */
const AGENT_HOST_KEY = Symbol.for("fradser.pi-subagents.agent-host");

interface AgentHostCarrier {
  [AGENT_HOST_KEY]?: AgentHost;
}

function carrier(): AgentHostCarrier {
  return globalThis as AgentHostCarrier;
}

/** Publish the coordinator's richer spawn path. Called by a team runtime at
 *  session start; absent leaves this tool on the raw spawner. */
export function setAgentHost(host: AgentHost | undefined): void {
  if (host === undefined) delete carrier()[AGENT_HOST_KEY];
  else carrier()[AGENT_HOST_KEY] = host;
}

export function resolveAgentHost(): AgentHost | undefined {
  return carrier()[AGENT_HOST_KEY];
}

const NAME_PATTERN = /^[a-z][a-z0-9._-]{0,63}$/i;

/** What an idle resident is doing, in the row's own words. Mirrors the receipt
 *  line the model reads, so a person and the model are never told different
 *  things about a child that is up and waiting. */
const IDLE_NOTICE = "no prompt; it will take work assigned to it";

/** One line describing how a child ended, for the roster entry it leaves behind. */
function describeExit(result: { exitCode?: number | null; signal?: string | null; stderr?: string }): string {
  if (result.signal) return `Child process ended on ${result.signal}.`;
  const code = result.exitCode ?? 0;
  const detail = result.stderr?.trim();
  return detail
    ? `Child process exited with ${code}: ${detail}`
    : `Child process exited with ${code}.`;
}

/** The first line of a prompt, for a one-line row. A prompt is the deliverable
 *  of a start, so naming it matters more than its length. */
function firstLine(text: string): string {
  const line = text.trim().split("\n")[0] ?? "";
  return line.length > 120 ? `${line.slice(0, 117)}…` : line;
}

const nameField = {
  type: "string",
  minLength: 1,
  maxLength: 64,
  pattern: "^[A-Za-z][A-Za-z0-9._-]*$",
  description: "Agent name: letters first, then letters, digits, dots, dashes, underscores.",
};

const sessionField = {
  type: "string",
  minLength: 1,
  description: "Exact session handle, as returned by start or list. One incarnation, permanently.",
};

const toolsField = {
  type: "array",
  items: { type: "string" },
  description: `Explicit minimal tool grant. Canonical built-ins: ${WORKER_BUILTIN_TOOLS.join(", ")}. Omit for the role's own grant, or pass [] for a child with no file or shell access.`,
};

/** A flat schema. The only nesting is the inline role definition, which is
 *  genuinely structured rather than a string that has to be re-parsed. */
export const AGENT_TOOL_PARAMS = {
  type: "object",
  properties: {
    action: {
      type: "string",
      enum: ["start", "inspect", "list", "stop"],
      description: "start spawns a child; inspect reports one incarnation; list enumerates children; stop terminates one incarnation.",
    },
    name: { ...nameField, description: "start: the new agent's name. inspect: unused; use session." },
    prompt: {
      type: "string",
      description: "start: hand the agent something to do now. Omit to leave it idle, waiting for work assigned to it.",
    },
    session: sessionField,
    description: { type: "string", description: "start: what the role is for, when no persisted definition matches the name." },
    role_prompt: { type: "string", description: "start: the role's standing instructions." },
    tools: { ...toolsField, description: "start: minimal grant for an inline role." },
    model: { type: "string", description: "start: provider/model pin, or omit to inherit." },
    fork: {
      type: "boolean",
      description: "start: seed the child with a snapshot of this session's active context. Legal with or without a prompt.",
    },
  },
  required: ["action"],
  additionalProperties: false,
} as const;

interface AgentToolResult {
  content: Array<{ type: "text"; text: string }>;
  details: Record<string, unknown>;
  isError?: boolean;
}

function fail(message: string): AgentToolResult {
  return { content: [{ type: "text", text: message }], details: { ok: false, error: message }, isError: true };
}

function ok(body: string, details: Record<string, unknown>): AgentToolResult {
  return { content: [{ type: "text", text: body }], details: { ...details, ok: true } };
}

/** The projected view of one child. `tools` is included because the effective
 *  grant is the one thing a caller routinely gets wrong by assumption. */
function project(teammate: Teammate) {
  return {
    name: teammate.name,
    session: teammate.spawnId ? exactSessionRoute(teammate.name, teammate.spawnId) : undefined,
    status: teammate.status,
    role: teammate.agent,
    ...(teammate.currentTaskId ? { currentTaskId: teammate.currentTaskId } : {}),
    ...(teammate.assignment ? { assignment: teammate.assignment } : {}),
    ...(teammate.tools ? { tools: teammate.tools } : {}),
    ...(teammate.model ? { model: teammate.model } : {}),
    ...(teammate.activeTool ? { activeTool: teammate.activeTool } : {}),
    // The child's own words, so a result has a second read after it has been
    // delivered. Bounded by the same cap the delivered message uses.
    ...(teammate.liveText?.trim() ? { liveText: teammate.liveText } : {}),
    ...(teammate.pid ? { pid: teammate.pid } : {}),
    ...(teammate.error ? { error: teammate.error } : {}),
  };
}

/**
 * The row for one `agent` result.
 *
 * Built as a named spec rather than inline so the renderer can be attached only
 * when the caller can supply real terminal geometry. A row built without geometry
 * renders in every offline test and then fails on the first real repaint, because
 * `--print` never paints a frame.
 */
const agentRowSpec: Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"] = (result) => {
  const details = (result.details ?? {}) as {
    name?: string;
    agent?: string;
    session?: string;
    status?: string;
    role?: string;
    model?: string;
    grant?: string[];
    prompt?: string;
    prompted?: boolean;
    outcome?: string;
    body?: string;
    count?: number;
    evidence?: string;
    agents?: Array<{ name: string; status: string; activeTool?: string }>;
    sessions?: Array<{ name: string; status: string; activeTool?: string }>;
  };
  const content = (result.content ?? []) as Array<{ text?: string }>;
  const text = content.map((part) => part.text ?? "").join("\n");
  // The prompt is the deliverable of a start, so it leads; everything after it on
  // the first line is a receipt, and a collapsed row that lists its own receipts
  // is noise. A handle never appears collapsed.
  const carried = text
    .split("\n")
    .filter(Boolean)
    .filter((line) => !/session:[^\s]+/.test(line))
    .map((line) => line.replace(/^WORKING · /, ""))
    .filter((line) => !/^(AGENT|IDLE|GRANT|ROLE) ·/.test(line));
  // A presence row leads with who is what, then what they are doing right now. The
  // activity line is the whole point of `inspect`: it is how a leader sees
  // progress without spending a turn asking.
  const described = (agent: { name: string; status: string; activeTool?: string }) =>
    [`- @${agent.name} · ${agent.status}`, ...(agent.activeTool ? [`now · ${agent.activeTool}`] : [])];
  const summary = details.agents
    ? details.agents.flatMap(described)
    : details.sessions
      ? details.sessions.flatMap(described)
      // An idle resident has no prompt to lead with, and the filter above
      // dropped the receipt line that said so. The row is a person's view of the
      // same fact, so it states it: a child that is up and waiting for work is
      // the case most easily mistaken for one that lost its work.
      : carried.length > 0 || details.prompted !== false
        ? carried
        : [IDLE_NOTICE];
  const stateWord = details.outcome === "stopped" ? "stopped" : undefined;
  return {
    kind: "started",
    tool: "agent",
    // Name then state, in one subject line: the renderer puts a label before the
    // subject, and splitting them would read `stopped · @reviewer`.
    subject: `${details.name || details.agent ? `@${details.name ?? details.agent}` : "agent"}${stateWord ? ` · ${stateWord}` : ""}`,
    ...(details.outcome && !stateWord ? { label: details.outcome } : {}),
    summary,
    details: [
      ...(details.role ? [`role · ${details.role}`] : []),
      ...(details.model ? [`model · ${details.model}`] : []),
      ...(details.grant?.length ? [`tools · ${details.grant.join(", ")}`] : []),
      // A child with no file or shell access cannot do implementation work. Saying
      // so on the row is the difference between a caller noticing and a child that
      // quietly cannot read anything.
      ...(details.grant && !details.grant.some((tool) => WORKER_BUILTIN_TOOLS.includes(tool as never))
        ? ["warning · coordination-only: no file or shell tools granted. Delegate implementation work with explicit canonical tools; no bash is granted by default."]
        : []),
      // The shutdown summary the runtime reported, then the caveat: a dead process
      // is not a finished task, and that is the mistake a reader would make.
      ...(details.body ? [details.body] : []),
      ...(details.outcome === "stopped"
        ? ["note · a stopped process is not evidence the work completed; check the task board"]
        : []),
      // Expansion reveals the whole prompt. The collapsed row shows its first line,
      // which is the deliverable; dropping the tail would mean the row could never
      // show what was asked.
      ...(details.prompt ? details.prompt.trim().split("\n").slice(1) : []),
    ],
  };
};

export interface AgentToolOptions {
  cwd?: string;
  /** Injectable so the surface is testable without a real child process. */
  /**
   * Builds the result renderer from a spec. Supplied by the extension entry, which
   * is the only layer allowed to import the TUI: a row needs real terminal
   * geometry, and a renderer without it builds a layout the host cannot draw.
   *
   * Absent means no custom renderer at all, so a headless caller gets Pi's own
   * default rather than a row that would fail on the first repaint.
   */
  renderResult?: (spec: { createSpec: Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"] }) => unknown;
  spawn?: typeof spawnResident;
  terminate?: typeof terminateTeammate;
  /**
   * Hands one settled child turn, or one child that ended without one, to the
   * Leader's session. Supplied by the loaded extension entry, which is the only
   * layer holding the session API; absent means the library spawns and records
   * without delivering, which is what a consumer embedding it directly gets.
   *
   * Ignored when a coordinator host is published: the host owns the spawn and
   * the report, and a second copy of every result is worse than none.
   */
  deliverSessionResult?: SessionNoticeSender;
  contextMessages?: () => unknown;
}

/** The parameter names the schema declares. A caller that invents one is either
 *  confused about the surface or coming from an older version of it, and both are
 *  worth a refusal rather than a silent drop. */
const KNOWN_PARAMS = new Set(Object.keys(AGENT_TOOL_PARAMS.properties));

export async function executeAgentAction(
  params: Record<string, unknown>,
  options: AgentToolOptions = {},
): Promise<AgentToolResult> {
  const unknownFields = Object.keys(params).filter((key) => !KNOWN_PARAMS.has(key));
  if (unknownFields.length > 0) {
    return fail(
      `Unknown agent parameter${unknownFields.length === 1 ? "" : "s"}: ${unknownFields.join(", ")}. `
      + `This tool takes: ${[...KNOWN_PARAMS].sort().join(", ")}.`,
    );
  }
  const action = typeof params.action === "string" ? params.action : "";
  const str = (key: string): string | undefined => {
    const value = params[key];
    return typeof value === "string" && value.trim() ? value.trim() : undefined;
  };
  const strArray = (key: string): string[] | undefined => {
    const value = params[key];
    if (value === undefined) return undefined;
    if (!Array.isArray(value)) throw new Error(`Parameter "${key}" must be an array of strings.`);
    return value.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0);
  };

  if (action === "start") {
    const name = str("name");
    if (!name) return fail("Starting an agent requires a name.");
    if (!NAME_PATTERN.test(name)) {
      return fail(`Invalid agent name "${name}". Use letters, digits, dots, dashes, underscores.`);
    }
    const description = str("description");
    const rolePrompt = str("role_prompt");
    if ((description === undefined) !== (rolePrompt === undefined)) {
      return fail("An inline role needs both description and role_prompt, or neither. Omit both to use a persisted definition.");
    }
    const resolved = resolveAgent(name, options.cwd);
    // No definition is not an error, and neither is no prompt. `start` with only
    // a name is the idle-resident case: a child that will take work assigned to
    // it. Demanding a role or a prompt first would make the two normal spawn
    // shapes — do this one thing, or sit ready for work — the exceptional ones.
    // The effective grant is reported back so the caller can see what it got.
    const synthesised = !resolved;
    const request: AgentStartRequest = {
      name,
      ...(str("prompt") ? { prompt: str("prompt") } : {}),
      ...(description && rolePrompt
        ? {
          definition: {
            description,
            prompt: rolePrompt,
            ...(strArray("tools") ? { tools: strArray("tools") } : {}),
            ...(str("model") ? { model: str("model") } : {}),
          },
        }
        : {}),
      ...(resolved ? { agent: resolved } as never : {}),
      ...(str("model") ? { model: str("model") } : {}),
      ...(strArray("tools") ? { tools: strArray("tools") } : {}),
      ...(params.fork === true ? { fork: true } : {}),
    };

    // Prefer the coordinator when one is loaded: it owns assignment authority,
    // board notices, and the fresh-session rule a team depends on.
    const host = resolveAgentHost();
    if (host) {
      const started = await host.start(request);
      if (!started.ok) return fail(started.error);
      // Report the grant the roster recorded, not the one that was asked for.
      // The two can differ when a coordinator narrows a request, and a caller
      // that assumed a tool it did not get is the failure this prevents — so
      // this is read back rather than echoed.
      const recorded = getTeammate(name);
      const grant = recorded?.tools ?? [];
      return ok(
        [
          `AGENT · ${name} · started · ${started.session}`,
          ...(request.prompt ? [`WORKING · ${firstLine(request.prompt)}`] : [`IDLE · ${IDLE_NOTICE}`]),
          `GRANT · ${grant.length > 0 ? grant.join(", ") : "coordination only"}`,
          // Say so plainly when the child has no standing instructions, on this
          // path too. It is the caller's only signal, and a later turn spent
          // re-explaining it is a turn wasted.
          ...(synthesised && !rolePrompt ? ["ROLE · none given; this child has only its prompt"] : []),
        ].join("\n"),
        {
          action: "start", outcome: "started", name, session: started.session,
          prompted: Boolean(request.prompt), role: recorded?.agent,
          ...(request.prompt ? { prompt: request.prompt } : {}),
          ...(recorded?.model ? { model: recorded.model } : {}),
          grant, synthesisedRole: synthesised,
        },
      );
    }

    // Standalone: the raw spawner, with the roster as the only coordination.
    const spawn = options.spawn ?? spawnResident;
    const definition = resolved ?? {
      name,
      description: description ?? name,
      prompt: rolePrompt ?? "",
      tools: strArray("tools") ?? [],
    };
    // The role reaches the child by *name*: it is registered as a session agent,
    // which is what the child's own worker extension resolves. Handing it to the
    // spawner instead would be silently dropped, because the spawner has no such
    // parameter, and the child would start with no role at all.
    // Only when there is a role to register. An idle resident started with no
    // prompt and no definition has none, and registering a placeholder with an
    // empty prompt would be refused — and would be wrong if it were not: a child
    // that resolved a role with no instructions would report a result nobody
    // asked for. The receipt already says so with `ROLE · none given`.
    if (definition.prompt.trim()) {
      try {
        registerSessionAgent({
          name,
          description: definition.description,
          prompt: definition.prompt,
          tools: definition.tools,
          ...(str("model") || request.definition?.model
            ? { model: str("model") ?? request.definition?.model }
            : {}),
        });
      } catch (error) {
        return fail(error instanceof Error ? error.message : String(error));
      }
    }

    // Claim the name *before* spawning. The roster is the only thing standing
    // between two same-named children, and checking after the spawn would leave
    // an orphan process running with no roster entry to stop it by.
    const spawnId = randomUUID();
    const now = Date.now();
    // Delivery bookkeeping for this incarnation only. A replacement incarnation
    // under the same name gets a fresh closure, so a retired child's late frame
    // can neither deliver nor be counted as the successor's.
    const session = exactSessionRoute(name, spawnId);
    const deliverSessionResult = options.deliverSessionResult;
    let settledTurns = 0;
    let deliveredThisTurn = false;
    // Whether the turn now in flight has been answered. Per turn, not per
    // incarnation: a Work Session that answered turn 1 and then died answering
    // turn 2 has still left the Leader a question with no answer.
    let turnAnswered = false;
    /** Only the incarnation that holds the name may write to it. A late close
     *  from a retired child must not stop its living replacement. */
    const isCurrent = () => getTeammate(name)?.spawnId === spawnId;
    const notice = (result: SessionResultNotice | SessionEndedNotice): boolean => {
      if (!deliverSessionResult) return false;
      try {
        deliverSessionResult(result);
        return true;
      } catch (error) {
        // A delivery failure must not take the roster with it: the Work Session
        // is real whether or not the Leader's session accepted its answer, and
        // the roster still holds the text.
        if (isCurrent()) {
          updateTeammate(name, {
            error: `Session Result delivery failed: ${error instanceof Error ? error.message : String(error)}`,
          });
        }
        return false;
      }
    };
    const reservation = registerTeammate({
      name,
      agent: definition.name,
      spawnId,
      pid: 0,
      status: "starting",
      isolation: "none",
      ...(strArray("tools") ? { tools: strArray("tools") } : {}),
      ...(request.fork ? { context: "fork" as const } : {}),
      createdAt: now,
      updatedAt: now,
    });
    if (!reservation.ok) return fail(reservation.error);

    // The kickoff prompt is the spawn's own `description`: the spawner writes it
    // to the child's control stream and opens the turn baseline there.
    // Delivering it a second time through `deliverPrompt` ran the same turn
    // twice — twice the child's tokens, and twice the Leader's turns once a
    // settled turn is delivered as a Session Result.
    const spawned = spawn({
      workerName: name,
      ...(request.prompt ? { description: request.prompt } : {}),
      ...(str("model") ? { model: str("model") } : {}),
      ...(strArray("tools") ? { tools: strArray("tools") } : {}),
      ...(params.fork === true && options.contextMessages
        ? { context: options.contextMessages() as never }
        : {}),
      // A settled turn is one result, not one per frame. The dedupe is armed by
      // the turn and released by the next one, and a settle carrying no text
      // does neither: a real child settles empty before it settles with its
      // answer, and treating that empty settle as the turn's result would
      // suppress the answer for the life of the Work Session.
      onUpdate: (update) => {
        if (!isCurrent()) return;
        updateTeammateProgress(name, spawnId, {
          liveText: update.text,
          liveThinking: update.liveThinking,
          activeTool: update.activeTool,
          turns: update.turns,
          sequenceEnded: update.finalResponse,
          modelOutputSeen: update.modelOutputSeen,
          usage: update.usage,
        });
        if (update.finalResponse === false) {
          deliveredThisTurn = false;
          turnAnswered = false;
          return;
        }
        // Nothing to say is not a result, and it is not this turn's one delivery
        // either: the answer may still be coming.
        if (update.finalResponse !== true || deliveredThisTurn || !update.text.trim()) return;
        deliveredThisTurn = true;
        settledTurns += 1;
        // A settled turn is not work in progress. The roster transitions itself
        // out of `starting`, and only on that first transition, so a child that
        // answered would otherwise be listed as working forever.
        if (update.finalResponse && getTeammate(name)?.status !== "idle") {
          updateTeammate(name, { status: "idle", activeTool: undefined });
        }
        // Counted as answered only once the Leader's session has taken it: a
        // result lost in delivery is still lost, and pretending otherwise would
        // also silence the notice a later death owes the Leader.
        if (notice({
          kind: "result", name, session, turn: settledTurns, text: update.text,
          ...(update.usage ? { usage: update.usage } : {}),
          deliveredAt: Date.now(),
        })) turnAnswered = true;
      },
      // A child that exits leaves the roster. Without this the name stays held by a
      // process that no longer exists, and a later start of the same name is
      // refused against a dead entry.
      onExit: (result) => {
        if (!isCurrent()) return;
        const reason = describeExit(result);
        updateTeammate(name, { status: "stopped", error: reason });
        // A shutdown the Leader asked for is not news: it already has a receipt
        // from `action=stop`, and painting it on the failure band would report a
        // planned stop as a death.
        if (turnAnswered || getTeammate(name)?.leaderRequestedEnd) return;
        // A death the Leader never heard about is a request that will never be
        // answered. Visible, but not a turn: recoverable execution stays internal.
        notice({ kind: "ended", name, session, reason, deliveredAt: Date.now() });
      },
      onError: (error) => {
        if (!isCurrent()) return;
        updateTeammate(name, { status: "stopped", error: error.message });
        if (turnAnswered) return;
        notice({
          kind: "ended", name, session,
          reason: `The Work Session could not be confirmed: ${error.message}`,
          deliveredAt: Date.now(),
        });
      },
    });
    if ("error" in spawned) {
      // Release the reservation. A name that stays reserved by a child which
      // never started is the worst outcome: the name looks taken and nothing is
      // running under it — and the reason belongs on the entry, or the roster
      // holds a name that looks taken with nothing to explain it.
      updateTeammate(name, { status: "stopped", error: spawned.error });
      return fail(`${spawned.error} @${name} was not started.`);
    }
    updateTeammate(name, { pid: spawned.pid, ...(spawned.envPolicy ? { envPolicy: spawned.envPolicy } : {}) });
    if (!request.prompt) updateTeammate(name, { status: "idle" });
    const grant = strArray("tools") ?? [];
    return ok(
      [
        `AGENT · ${name} · started · ${session}`,
        ...(request.prompt ? [`WORKING · ${firstLine(request.prompt)}`] : [`IDLE · ${IDLE_NOTICE}`]),
        `GRANT · ${grant.length > 0 ? grant.join(", ") : "coordination only"}`,
        // Say so plainly when the child has no standing instructions, on this
        // path too. It is the caller's only signal, and a later turn spent
        // re-explaining it is a turn wasted.
        ...(synthesised && !rolePrompt ? ["ROLE · none given; this child has only its prompt"] : []),
      ].join("\n"),
      {
        action: "start", outcome: "started", name, session,
        prompted: Boolean(request.prompt), standalone: true,
        ...(request.prompt ? { prompt: request.prompt } : {}),
        role: name,
        ...(str("model") ? { model: str("model") } : {}),
        grant, synthesisedRole: synthesised,
      },
    );
  }

  if (action === "inspect") {
    const session = str("session");
    if (!session) {
      const named = str("name");
      const live = named ? livingTeammates().find((t) => t.name === named) : undefined;
      const living = livingTeammates();
      return fail(
        "Inspecting an agent requires its exact session handle, so a retired incarnation cannot be "
        + `mistaken for its replacement.${live ? ` @${live.name} is ${exactSessionRoute(live.name, live.spawnId!)}.` : ""}`
        + (living.length > 0 ? ` Run agent action=list to see the current handles.` : ""),
      );
    }
    const matched = resolveExactSession(session, listTeammates());
    if (!matched) {
      const parsed = parseExactSessionRoute(session);
      const replacement = parsed ? livingTeammates().find((t) => t.name === parsed.name) : undefined;
      return fail(
        replacement
          ? `No living session "${session}". @${replacement.name} is now ${exactSessionRoute(replacement.name, replacement.spawnId!)}.`
          : `No living session "${session}".`,
      );
    }
    return ok(`AGENT · ${matched.name} · ${matched.status} · ${session}`, { action: "inspect", outcome: "inspected", agent: matched.name, sessions: [project(matched)] });
  }

  if (action === "list") {
    const all = listTeammates();
    return ok(
      all.length === 0
        ? "AGENT · none"
        : all.map((t) => `- @${t.name} · ${t.status} · ${t.spawnId ? exactSessionRoute(t.name, t.spawnId) : "(no incarnation)"}`).join("\n"),
      { action: "list", outcome: "listed", count: all.length, agents: all.map(project) },
    );
  }

  if (action === "stop") {
    const session = str("session");
    if (!session) return fail("Stopping an agent requires its exact session handle. Run agent action=list to see the current handles.");
    const matched = resolveExactSession(session, listTeammates());
    if (!matched) return fail(`No living session named "${session}".`);
    const host = resolveAgentHost();
    let closed: { ok: true; body?: string } | { ok: false; error: string };
    if (host) {
      closed = await host.stop(matched.name, matched.spawnId);
    } else {
      // A missing process is reported rather than treated as success: the caller
      // asked to stop a specific incarnation and nothing confirmed it closed.
      const outcome = await (options.terminate ?? terminateTeammate)(matched.name);
      closed = outcome.outcome === "missing"
        ? { ok: false, error: `No child process named "${matched.name}" is running.` }
        : outcome.outcome === "unconfirmed"
          ? { ok: false, error: `@${matched.name} did not confirm it closed. Inspect the process before assuming it stopped.` }
          : { ok: true };
    }
    if (!closed.ok) return fail(closed.error);
    // Mark the ending as requested before the close lands, so the child's exit
    // is recognised as the shutdown it is rather than reported as a death the
    // Leader never heard about. `action=stop`'s own receipt is the report.
    updateTeammate(matched.name, { status: "stopped", leaderRequestedEnd: true });
    return ok(
      `AGENT · @${matched.name} · stopped`,
      // A stopped process is not a completed task. Saying so here is cheaper
      // than the model inferring completion from a silent process exit.
      { action: "stop", outcome: "stopped", session, name: matched.name, agent: matched.name,
        ...(closed.body ? { body: closed.body } : {}), evidence: "Process terminated. This is not evidence the work completed; check the task board." },
    );
  }

  return fail(`Unknown agent action "${action}". Use start, inspect, list, or stop.`);
}

/** Publish the roster as the board's participant registry.
 *
 * Only when no coordinator has claimed the store, so a team runtime that counts
 * board revisions keeps its own policy. Without this, installing the execution
 * layer and the board together would leave the board with no conflict oracle and
 * it would degrade to single-session, which is the wrong degradation: a roster
 * exists, so there is something to check against.
 */
function publishRosterAsBoardStore(): void {
  configureBoardStoreIfUnset({
    get: (holder) => {
      const entry = getTeammate(holder);
      return entry ? { name: entry.name, spawnId: entry.spawnId, status: entry.status } : undefined;
    },
    conflicting: (resources, except) => {
      for (const entry of livingTeammates()) {
        if (entry.name === except) continue;
        const assignment = entry.assignment as WorkAssignment | undefined;
        if (assignment && !assignment.closed && resourcesConflict(resources, assignment.resources)) {
          return { name: entry.name, spawnId: entry.spawnId, status: entry.status };
        }
      }
      return undefined;
    },
    sync: (holder, assignment, taskId) => {
      updateTeammate(holder, {
        ...(assignment ? { assignment } : { assignment: undefined }),
        ...(taskId ? { currentTaskId: taskId } : { currentTaskId: undefined }),
      });
    },
    // A library has no snapshot writer, so there is nothing to mark changed.
    changed: () => {},
  });
}

/** The single registrant of `agent`. */
export function registerAgentTool(pi: ExtensionAPI, options: AgentToolOptions = {}): void {
  publishRosterAsBoardStore();
  pi.registerTool({
    name: "agent",
    label: "Agent",
    promptSnippet: "Start, inspect, list, or stop a child agent process",
    description: "Child process lifecycle. start spawns an agent; pass a prompt and it works immediately, omit it and it stays idle waiting for work assigned to it. inspect and stop take an exact session handle and address one incarnation. Results arrive automatically: continue your own work or end the turn rather than polling, sleeping, or repeatedly inspecting a child to learn what was already delivered.",
    parameters: AGENT_TOOL_PARAMS as never,
    renderShell: "self",
    // A start can take a while, and a stopped child is a state change worth one
    // line. Rendering through the shared lifecycle renderer keeps the row shape
    // identical to the other coordination tools instead of inventing a fourth.
    renderCall: emptyToolCall,
    // Attached only when the caller can supply real geometry. A row built without
    // it is worse than no row: it renders in tests and takes the terminal down on
    // the first repaint.
    ...(options.renderResult ? { renderResult: options.renderResult({ createSpec: agentRowSpec }) as never } : {}),

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      return executeAgentAction(params as Record<string, unknown>, {
        ...options,
        cwd: options.cwd ?? ctx?.cwd,
        contextMessages: options.contextMessages ?? (() => snapshotWorkContext(ctx?.sessionManager)),
      });
    },
  });
}
