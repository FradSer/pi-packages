/**
 * The Pi extension body for `@fradser/pi-subagents`.
 *
 * Lives in `src/` so `index.ts` can re-export it as the package's default export,
 * which is what lets one file serve as both the library entry and the extension
 * entry. A separate top-level extension file would split that, and the root
 * `index.ts` is what every other runtime package here loads.
 *
 * It registers exactly one tool and owns the delivery of a settled child's
 * Session Result back into this session. A team runtime can publish a richer
 * spawn path through `setAgentHost`; without one, `agent` falls back to the raw
 * spawner, which is what makes this package usable alone.
 *
 * Deliberately keeps the tool library TUI-free, and injects only the row
 * binding from `./rows.ts`. `agent-tool.ts` is imported by the headless suites
 * and by other packages, so the geometry it needs has to arrive as a parameter;
 * the entry is the one layer that is only ever loaded by Pi, so it is the one
 * layer allowed to import pi-tui. A row without real geometry is worse than no
 * row at all — it renders in an offline fixture and takes the terminal down on
 * the first repaint — which is why this file supplies it instead of leaving the
 * `agent` result to Pi's default receipt rendering.
 *
 * The entry is also where a Session Result is sent. A tool's execution context
 * has no `sendMessage`, so the session API reaches the library only from here,
 * and a consumer embedding the library without this entry gets spawning without
 * delivery. See ADR-0007.
 */

import { registerAgentTool } from "./agent-tool.ts";
import { createAgentResultRenderer, createSessionMessageRenderer } from "./rows.ts";
import type { LifecycleRendererBindings } from "@fradser/pi-kit";
import {
  SESSION_ENDED_MESSAGE_TYPE,
  SESSION_RESULT_MESSAGE_TYPE,
  formatSessionNotice,
  readSessionNotice,
  sessionNoticeMessageType,
  sessionNoticeSpec,
  unreadableSessionNoticeSpec,
  type SessionNoticeSender,
} from "./session-result.ts";

export default function piSubagents(pi: Parameters<typeof registerAgentTool>[0]): void {
  // Read per render: only a live session has a `ui` and a `cwd` for the host
  // wrapper, and a row rendered without them is a row the host cannot expand.
  let host: Pick<LifecycleRendererBindings, "ui" | "cwd"> = {};
  const noticeRenderer = () => createSessionMessageRenderer((details) => {
    const notice = readSessionNotice(details);
    return notice ? sessionNoticeSpec(notice) : unreadableSessionNoticeSpec();
  }, () => host);
  // Rendering a notice and delivering one are separate capabilities. A host that
  // cannot render still receives the result and paints it with its own default,
  // so the missing renderer must not take delivery down with it.
  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer(SESSION_RESULT_MESSAGE_TYPE, (message, state, theme) =>
      noticeRenderer()(message as never, state, theme));
    pi.registerMessageRenderer(SESSION_ENDED_MESSAGE_TYPE, (message, state, theme) =>
      noticeRenderer()(message as never, state, theme));
  }

  // Likewise a host with no session API still gets a working `agent` tool: it
  // spawns, records, and inspects, and delivers nothing. That is the library's
  // documented behaviour, not a degraded mode worth failing over.
  //
  // This is the only place a delivery can fail, so nothing is swallowed here: a
  // synchronous throw propagates to the caller, which records it on the roster,
  // and the promise `sendMessage` actually returns is consumed so an async
  // failure is never an unhandled rejection.
  const sender: SessionNoticeSender = typeof pi.sendMessage !== "function" ? () => {} : (notice) => {
    pi.sendMessage(
      {
        customType: sessionNoticeMessageType(notice),
        content: formatSessionNotice(notice),
        display: true,
        details: notice,
      },
      // A result is work the Leader asked for and is waiting on, so it enters
      // the next turn as a follow-up rather than interrupting a turn in flight.
      //
      // An ended Work Session is a terminal fact a person must be able to see,
      // never one the Leader has to decide about, and `triggerTurn: false` is
      // spelled out rather than left absent: absent means "not false", which pi
      // reads as permission to steer the turn in flight (ADR-0002). `nextTurn`
      // queues it without interrupting, so the line is visible in the next
      // turn's context and costs no turn of its own.
      notice.kind === "result"
        ? { deliverAs: "followUp", triggerTurn: true }
        : { deliverAs: "nextTurn", triggerTurn: false },
    );
  };

  registerAgentTool(pi, { renderResult: createAgentResultRenderer, deliverSessionResult: sender });
  pi.on("model_select", async (_event, ctx) => { if (ctx) host = ctx; });
  pi.on("thinking_level_select", async (_event, ctx) => { if (ctx) host = ctx; });
  pi.on("session_start", async (_event, ctx) => {
    if (ctx) host = ctx;
    pi.events.emit("pi-subagents:ready", {});
  });
}
